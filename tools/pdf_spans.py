"""Keep actual PDF font changes which structured-text span merging can lose."""
import pymupdf as fitz
import io
from fontTools.cffLib import CFFFontSet
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from bisect import bisect_left,bisect_right
from collections import defaultdict

_font_ink_cache={}
_page_fonts_cache={}
_punctuation_fonts={}


def ink_x(page,font,gid,origin,size,bbox,char=None):
    """Type1 character origins can lie after the following printed glyph.

    Use the embedded outline's bearings for horizontal reading order. Keep
    source baselines and vertical boxes, which drive paragraph grouping.
    """
    damaged=font in {'FzBookMaker0DlFont0','FzBookMaker1DlFont1','FzBookMaker2DlFont2','FzBookMaker13DlFont13','FzBookMaker14DlFont14','FzBookMaker15DlFont15'}
    if not damaged and (not char or char not in '（）［］【】「」『』，、。；：'):return bbox
    page_key=(page.parent.name,page.number)
    if page_key not in _page_fonts_cache:_page_fonts_cache[page_key]=page.get_fonts(full=True)
    choices=[f for f in _page_fonts_cache[page_key] if font in f[3]]
    if len(choices)!=1:return bbox
    xref=choices[0][0];key=(page.parent.name,xref)
    if not damaged:
        if key not in _punctuation_fonts:
            _,extension,_,raw=page.parent.extract_font(xref)
            if extension!='ttf':_punctuation_fonts[key]=None
            else:
                face=TTFont(io.BytesIO(raw));_punctuation_fonts[key]=(face.getGlyphSet(),face.getGlyphOrder(),face['head'].unitsPerEm,{})
        record=_punctuation_fonts[key]
        if record is None:return bbox
        glyphs,names,em,cache=record
        if not 0<=gid<len(names):return bbox
        if gid not in cache:
            pen=BoundsPen(glyphs);glyphs[names[gid]].draw(pen);cache[gid]=pen.bounds
        b=cache[gid]
        return (origin[0]+b[0]*size/em,bbox[1],origin[0]+b[2]*size/em,bbox[3]) if b else bbox
    if key not in _font_ink_cache:
        cff=CFFFontSet();cff.decompile(io.BytesIO(page.parent.extract_font(xref)[3]),None);top=cff[cff.fontNames[0]]
        _font_ink_cache[key]=(top,{})
    top,bounds=_font_ink_cache[key]
    if gid not in bounds:
        pen=BoundsPen(top.CharStrings);top.CharStrings[top.charset[gid]].draw(pen);bounds[gid]=pen.bounds
    b=bounds[gid]
    if not b:return bbox
    matrix=top.FontMatrix
    return (origin[0]+b[0]*matrix[0]*size,bbox[1],origin[0]+b[2]*matrix[0]*size,bbox[3])


def traced_spans(page):
    if hasattr(page,'_traced_spans'):return [dict(s) for s in page._traced_spans]
    output=[]
    for trace in page.get_texttrace():
        current=None
        for unicode,gid,origin,bbox in trace['chars']:
            text=chr(unicode) if 0<=unicode<=0x10ffff else '□'
            original_bbox=bbox
            if abs(trace['dir'][1])<.001:bbox=ink_x(page,trace['font'],gid,origin,trace['size'],bbox,text)
            if current is not None:
                previous=current['_glyphs'][-1]
                if abs(origin[1]-previous['origin'][1])>.3 or origin[0]<previous['origin'][0]-.2 or origin[0]-previous['origin'][0]>trace['size']*2:
                    output.append(current);current=None
            if current is None:
                current={'font':trace['font'],'size':trace['size'],'flags':trace['flags'],
                         'text':'','source_text':'','origin':origin,'bbox':bbox,'_glyphs':[]}
            current['text']+=text;current['source_text']+=text
            current['bbox']=tuple(fitz.Rect(current['bbox'])|fitz.Rect(bbox))
            current['_glyphs'].append({'c':text,'origin':origin,'bbox':bbox,'_advance_bbox':original_bbox,'gid':gid})
        if current is not None:output.append(current)
    # A trace can batch the same font across an intervening parenthesis or
    # subscript drawn with another font. Split at those real glyph positions
    # before callers sort runs horizontally (minE + '(' must stay min(E)).
    bins=defaultdict(list)
    for owner,span in enumerate(output):
        for glyph in span['_glyphs']:bins[round(glyph['origin'][1]/4)].append((glyph['bbox'][0],glyph['origin'][1],owner))
    split=[]
    for owner,span in enumerate(output):
        glyphs=span['_glyphs'];y=span['origin'][1];band=round(y/4)
        positions=sorted(x for key in range(band-2,band+3) for x,gy,other in bins[key] if other!=owner and abs(gy-y)<span['size']*.8)
        groups=[[]]
        for glyph in glyphs:
            if groups[-1]:
                x0=groups[-1][-1]['bbox'][0];x1=glyph['bbox'][0]
                if bisect_right(positions,x0+.05)<bisect_left(positions,x1-.05):groups.append([])
            groups[-1].append(glyph)
        for chars in groups:
            part=dict(span);part['_glyphs']=chars;part['text']=part['source_text']=''.join(g['c'] for g in chars)
            part['origin']=chars[0]['origin'];part['bbox']=(min(g['bbox'][0] for g in chars),min(g['bbox'][1] for g in chars),max(g['bbox'][2] for g in chars),max(g['bbox'][3] for g in chars))
            part['_advance_bbox']=(min(g['_advance_bbox'][0] for g in chars),min(g['_advance_bbox'][1] for g in chars),max(g['_advance_bbox'][2] for g in chars),max(g['_advance_bbox'][3] for g in chars))
            split.append(part)
    page._traced_spans=split
    return [dict(s) for s in split]
