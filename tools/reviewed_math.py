"""Source-checked transcriptions for equations with two-dimensional layout.

Coordinates are PDF points and remain stable when line grouping changes.
Every replaced line is retained in the paragraph provenance ledger.
"""
import json
import yaml
import re
import html
import statistics
from functools import lru_cache
from pathlib import Path
from paragraphs import rich_line
from native_math import source_text


def prepare_keywords(lines,code,page):
    pattern=re.compile(r'^(?:if|for|while)(?=[A-Za-z])|(?-i:(?<![a-z])to(?=[A-Z]))|(?<![A-Za-z])(?:end\s*(?:for|if|while)|else\s*if|for|while|if|else|return|to)(?![A-Za-z])',re.I)
    algorithms=[e['bbox'] for e in entries() if e['code']==code and e['page']==page and e.get('mode')=='algorithm']
    for line in lines:
        b=line['bbox'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
        if any(b[0]<=cx<=b[2] and b[1]<=cy<=b[3] for b in algorithms):line['_algorithm']=True
        if not re.match(r'^(?:if|for|while|else|end|return)\b|^(?:if|for|while)[A-Za-z(（]',line['text'],re.I):continue
        rebuilt=[]
        for span in line['spans']:
            value=source_text(span);matches=list(pattern.finditer(value))
            if not matches:rebuilt.append(span);continue
            if not span.get('_glyphs') and len(span['source_text'])==len(value):
                x0,y0,x1,y1=span['bbox'];step=(x1-x0)/max(1,len(value))
                span['_glyphs']=[{'c':raw,'origin':(x0+i*step,span['origin'][1]),'bbox':(x0+i*step,y0,x0+(i+1)*step,y1)} for i,raw in enumerate(span['source_text'])]
            if len(span.get('_glyphs',[]))!=len(value):rebuilt.append(span);continue
            cursor=0
            for match in matches+[None]:
                end=match.start() if match else len(value)
                for start,stop,keyword in [(cursor,end,False)]+([(match.start(),match.end(),True)] if match else []):
                    if start==stop:continue
                    part=dict(span);glyphs=span['_glyphs'][start:stop];part['_glyphs']=glyphs
                    part['source_text']=''.join(g['c'] for g in glyphs);part['text']=value[start:stop]
                    part['origin']=glyphs[0]['origin'];part['bbox']=(min(g['bbox'][0] for g in glyphs),min(g['bbox'][1] for g in glyphs),max(g['bbox'][2] for g in glyphs),max(g['bbox'][3] for g in glyphs))
                    if keyword:
                        word=re.sub(r'^(end)(for|if|while)$',r'\1 \2',part['text'],flags=re.I)
                        part['_html']=' '+html.escape(word)+' ';part['_math_handled']=True
                    rebuilt.append(part)
                if match:cursor=match.end()
            line['spans']=rebuilt


def numeric_code(line):
    glyphs=[]
    for span in line['spans']:
        decoded=source_text(span)
        if len(decoded)==len(span.get('_glyphs',[])):
            glyphs.extend((char,g['origin'][0],g['origin'][1],span['font']) for char,g in zip(decoded,span['_glyphs']))
    glyphs.sort(key=lambda g:g[1]);steps=[]
    for a,b in zip(glyphs,glyphs[1:]):
        if a[0].isdigit() and b[0].isdigit() and a[3]==b[3] and abs(a[2]-b[2])<1 and 1<b[1]-a[1]<8:steps.append(b[1]-a[1])
    step=statistics.median(steps) if steps else 5
    text='';previous=None
    for g in glyphs:
        if previous and previous[0].isdigit() and g[0].isdigit() and g[1]-previous[1]>step*1.35:text+=' '
        text+=g[0];previous=g
    return text or line['text']


def qam_latex(bits,norm,number):
    def bit(offset):return f'b({bits}i'+(f'+{offset}' if offset else '')+')'
    def branch(parity):
        if bits<=4:
            tail='[2-(1-2'+bit(2+parity)+')]' if bits==4 else ''
            return ['(2'+bit(parity)+'-1)'+tail]
        levels=bits//2-1
        rows=['(2'+bit(parity)+'-1)['+str(2**levels)]
        for offset in range(2+parity,bits-2+parity,2):
            if offset==bits-4+parity:
                rows.append('-(1-2'+bit(offset)+')[2-(1-2'+bit(bits-2+parity)+')'+']'*levels)
            else:rows.append('-(1-2'+bit(offset)+')['+str(2**((bits-offset+parity)//2-1)))
        return rows
    rows=[]
    for parity in (0,1):
        for index,part in enumerate(branch(parity)):
            rows.append('&'+(r'\qquad ' if index else '+j' if parity else '')+part)
    return r'd(i)=-\frac1{\sqrt{'+str(norm)+r'}}\left\{\begin{aligned}'+r'\\'.join(rows)+r'\end{aligned}\right\}\tag{'+str(number)+'}'


def inline(code,page,lines):
    for entry in entries():
        if not entry.get('inline') or entry['code']!=code or entry['page']!=page:continue
        box=entry['bbox'];selected=[]
        for line in lines:
            for span in line['spans']:
                b=span['bbox'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
                if box[0]<=cx<=box[2] and box[1]<=cy<=box[3]:selected.append((line,span))
        if not selected:raise ValueError(f'Empty inline math region: {entry}')
        target_line=min(selected,key=lambda pair:abs(pair[1]['origin'][1]-entry['anchor_y']))[0]
        anchor=min((s for l,s in selected if l is target_line),key=lambda s:s['bbox'][0])
        for _,span in selected:span['_html']='';span['_math_handled']=True
        anchor['_html']='$'+entry['latex']+'$';anchor['_native_math']=entry['latex']
        for line,_ in selected:
            if all(not s.get('_html',s['text']).strip() for s in line['spans']):
                line['_math_empty']=True
                line['_math_fragment_of']=next(i for i,l in enumerate(lines) if l is target_line)


@lru_cache(maxsize=1)
def entries():
    path=Path(__file__).resolve().parents[1]/'metadata/reviewed-math.json'
    extra=path.with_name('reviewed-math-extra.yml')
    content=path.with_name('201-reviewed-content.yml')
    return (json.loads(path.read_text())['regions'] if path.exists() else [])+(yaml.safe_load(extra.read_text()) if extra.exists() else [])+(yaml.safe_load(content.read_text()) if content.exists() else [])


def apply(code,page,lines,min_y,max_y,ledger,filename):
    events=[];regions=[];consumed=set()
    algorithms=[e for e in entries() if e['code']==code and e['page']==page and e.get('mode')=='algorithm']
    for entry in entries():
        if entry.get('inline'):continue
        if entry['code']!=code or entry['page']!=page:continue
        box=entry['bbox']
        if entry.get('mode')!='algorithm' and any(a['bbox'][0]<=box[0] and a['bbox'][1]<=box[1] and a['bbox'][2]>=box[2] and a['bbox'][3]>=box[3] for a in algorithms):continue
        if not min_y<=box[1]<max_y:continue
        source=[]
        for i,line in enumerate(lines):
            b=line['bbox'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
            if box[0]<=cx<=box[2] and box[1]<=cy<=box[3]:source.append((i,line))
        if not source:
            raise ValueError(f'Empty reviewed math region: {code} p{page} {box}')
        if entry.get('mode')=='algorithm':
            inner=[e for e in entries() if e['code']==code and e['page']==page and e is not entry and 'latex' in e and not e.get('inline') and box[0]<=e['bbox'][0] and box[1]<=e['bbox'][1] and box[2]>=e['bbox'][2] and box[3]>=e['bbox'][3]]
            rows=[];left=min(l['bbox'][0] for _,l in source)
            for i,line in source:
                b=line['bbox'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
                if any(e['bbox'][0]<=cx<=e['bbox'][2] and e['bbox'][1]<=cy<=e['bbox'][3] for e in inner):continue
                indent='&#8195;'*max(0,min(12,round((b[0]-left)/11)))
                rows.append((b[1],'<p>'+indent+rich_line(line)+'</p>'))
            for e in inner:rows.append((e['bbox'][1],'<p>$'+e['latex']+'$</p>'))
            markup=':::{div}\n:class: standard-algorithm\n\n'+'\n'.join(r[1] for r in sorted(rows))+'\n\n:::';kind='pseudocode'
        elif 'qam' in entry:
            bits,norm,number=entry['qam']
            value=qam_latex(bits,norm,number)
            markup='```{math}\n'+value+'\n```';kind='equation'
        elif 'latex' in entry:
            markup='```{math}\n'+entry['latex']+'\n```'
            kind='equation'
        elif entry.get('mode')=='code':
            markup='```text\n'+'\n'.join(numeric_code(l) if entry.get('numbers') else l['text'] for _,l in source)+'\n```';kind='pseudocode'
        else:markup=entry['markup'];kind=entry.get('kind','paragraph')
        events.append((box[1],0,markup));regions.append(box);consumed.update(i for i,_ in source)
        ledger.append({'page':page,'kind':kind,'line_ids':[i for i,_ in source],
                       'source_text':'\n'.join(l['text'] for _,l in source),'bbox':box,
                       'file':filename,'reviewed_math':True,
                       **({'reading_order_text':entry['reading_order_text']} if entry.get('reading_order_text') else {}),
                       **({'render_counts':entry['render_counts']} if entry.get('render_counts') else {})})
    return events,regions,consumed
