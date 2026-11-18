#!/usr/bin/env python3
"""Recover the broken PDF's glyph map using repeated OCR/geometry evidence."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE_TERMS={s.replace(' ',''):s for s in [
    'radio frame','first training signal','secondary training signal','phase adjustment signal',
    'physical layer identity','positioning anchor','positioning tag','positioning signal',
    'positioning symbol','ranging symbol','positioning frame','ranging frame',
    'single side positioning','double sides positioning','first positioning signal','second positioning signal']}


def load_map():
    path=ROOT/'metadata/201-font-map.json'
    if not path.exists():return {}
    mapping=json.loads(path.read_text())['mapping']
    # These frequent glyphs were checked in source body paragraphs. Blank
    # synthetic PDF characters are spaces, never OCR character candidates.
    mapping.update({'FzBookMaker8DlFont805368\tê':'的','FzBookMaker7DlFont705368\t&':'—',
                    'FzBookMaker8DlFont805368\t`':'入','FzBookMaker12DlFont12053\t4':'锚',
                    'FzBookMaker12DlFont12053\t"':'日',
                    'FzBookMaker12DlFont12053\t╛':'致','FzBookMaker12DlFont12053\tΓ':'荐',
                    'FzBookMaker12DlFont12053\tΣ':'己'})
    # These English terms were read directly from source pages 11–12. Their
    # consistent Type3 alphabet corrects the OCR n/m ambiguity throughout.
    verified=[('#$&','SLB'),('*):,3=*)4/','radioframe'),('=,*166*),-,-@1,@-)0','firsttrainingsignal'),
              ("A'#",'FTS'),('1/23-:)*76*),-,-@1,@-)0','secondarytrainingsignal'),("#'#",'STS'),
              ('(;)1/):B5164/-61,@-)0','phaseadjustmentsignal'),('8C#','PAS'),
              ('(;71,2)00)7/*,:/-6,67','physicallayeridentity'),('8!D','PID'),
              ('(31,6,3-,-@)-2;3*','positioninganchor'),('(31,6,3-,-@6)@','positioningtag'),
              ('(31,6,3-,-@1,@-)0','positioningsignal'),('(31,6,3-,-@174<30','positioningsymbol'),
              ('*)-@,-@174<30','rangingsymbol'),('(31,6,3-,-@=*)4/','positioningframe'),
              ('*)-@,-@=*)4/','rangingframe'),('1,-@0/1,:/(31,6,3-,-@','singlesidepositioning'),
              (':35<0/1,:/1(31,6,3-,-@','doublesidespositioning'),
              ('=,*16(31,6,3-,-@1,@-)0','firstpositioningsignal'),
              ('1/23-:(31,6,3-,-@1,@-)0','secondpositioningsignal')]
    checked={}
    for encoded,plain in verified:
        assert len(encoded)==len(plain)
        for a,b in zip(encoded,plain):
            assert a not in checked or checked[a]==b
            checked[a]=b
    mapping.update({'FzBookMaker0DlFont0\t'+a:b for a,b in checked.items()})
    verified_math=ROOT/'metadata/math-glyph-map.json'
    if verified_math.exists():mapping.update(json.loads(verified_math.read_text())['mapping'])
    verified_glyphs=ROOT/'metadata/201-verified-glyphs.json'
    if verified_glyphs.exists():mapping.update(json.loads(verified_glyphs.read_text())['mapping'])
    return mapping


def decode_span(span,mapping):
    font=span['font']
    text=''.join(mapping.get(font+'\t'+c,c if not font.startswith('FzBookMaker') else ' ' if c==' ' else '□') for c in span['text'])
    return SOURCE_TERMS.get(text,text) if font=='FzBookMaker0DlFont0' else text


def load_ocr():
    # Glyph recovery is frozen in the verified map. Only layout lines remain
    # necessary for Latin word boundaries and original raster-code detection.
    data=json.loads((ROOT/'metadata/201-layout-lines.json').read_text())
    return {int(page):[dict(line,chars=[]) for line in lines] for page,lines in data.items()}


def fallback_lines(page,lines,ocr):
    mapping=load_map()
    glyphs={}
    for block in page.get_text('rawdict')['blocks']:
        if block['type']!=0:continue
        for raw_line in block['lines']:
            for span in raw_line['spans']:
                key=(span['font'],round(span['origin'][0],2),round(span['origin'][1],2))
                glyphs[key]=span['chars']
    recognized=[]
    for item in ocr:
        for character,x0,y0,x1,y1 in item['chars']:
            if not character.strip():continue
            recognized.append((character,(x0+x1)*page.rect.width/2,(y0+y1)*page.rect.height/2,item['confidence']))
    for line in lines:
        changed=False
        for span in line['spans']:
            if '□' not in span['text']:continue
            key=(span['font'],round(span['origin'][0],2),round(span['origin'][1],2))
            chars=span.get('_glyphs',glyphs.get(key,[]))
            if len(chars)!=len(span['text']):continue
            decoded=list(span['text'])
            for i,(value,glyph) in enumerate(zip(decoded,chars)):
                if value!='□':continue
                box=glyph['bbox'];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
                candidates=[r for r in recognized if abs(r[1]-cx)<span['size']*.65 and abs(r[2]-cy)<span['size']*.6]
                if not candidates:continue
                best=min(candidates,key=lambda r:abs(r[1]-cx)+abs(r[2]-cy))
                decoded[i]=best[0];changed=True
            span['text']=''.join(decoded)
        if changed:
            parts=[];previous=None
            for span in line['spans']:
                if previous and span.get('_advance_bbox',span['bbox'])[0]-previous.get('_advance_bbox',previous['bbox'])[2]>1.5:parts.append(' ')
                parts.append(span['text']);previous=span
            line['text']=''.join(parts).strip()
            line['character_ocr']=True
        # Source glyph placement often omits literal word-space characters.
        # Transfer only OCR word boundaries when the Latin letters agree.
        for span in line['spans']:
            if span['font']!='FzBookMaker0DlFont0' or not re.fullmatch('[A-Za-z]+',span['text']):continue
            matches=[]
            for candidate in ocr:
                b=candidate['bbox'];cy=(b[1]+b[3])*page.rect.height/2
                if abs(cy-(span['bbox'][1]+span['bbox'][3])/2)>span['size']:continue
                for phrase in re.findall(r'[A-Za-z][A-Za-z ]*[A-Za-z]|[A-Za-z]',candidate['text']):
                    if phrase.replace(' ','').lower()==span['text'].lower():matches.append(phrase)
            if matches:span['text']=max(matches,key=lambda s:s.count(' '))
        parts=[];previous=None
        for span in line['spans']:
            if previous and span.get('_advance_bbox',span['bbox'])[0]-previous.get('_advance_bbox',previous['bbox'])[2]>1.5:parts.append(' ')
            parts.append(span['text']);previous=span
        line['text']=''.join(parts).strip()
        if '□' not in line['text']:continue
        box=line['bbox'];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
        candidates=[]
        for candidate in ocr:
            b=candidate['bbox'];r=[b[0]*page.rect.width,b[1]*page.rect.height,b[2]*page.rect.width,b[3]*page.rect.height]
            dy=abs((r[1]+r[3])/2-cy)
            overlap=max(0,min(box[2],r[2])-max(box[0],r[0]))/max(1,min(box[2]-box[0],r[2]-r[0]))
            if dy<max(8,(box[3]-box[1])*.6) and overlap>.55:candidates.append((dy,candidate))
        if not candidates:continue
        closest=min(x[0] for x in candidates)
        same_row=[c for dy,c in candidates if dy<closest+3]
        same_row.sort(key=lambda c:c['bbox'][0])
        text=' '.join(c['text'] for c in same_row)
        if sum('\u3400'<=c<='\u9fff' for c in text)<2:continue
        for a,b in [('媒体接人','媒体接入'),('多输人','多输入'),('输人','输入'),('接人层','接入层')]:text=text.replace(a,b)
        # Keep known glyphs even when one symbol remains unresolved. A whole
        # OCR row can replace a badly decoded heading, but must not overwrite
        # reliable body text because a single mathematical glyph is unknown.
        if line['text'].count('□')/max(1,len(line['text']))>.25:
            line.update(text=text,ocr=True,ocr_confidence=min(c['confidence'] for c in same_row))
    return lines
