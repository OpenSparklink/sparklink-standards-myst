#!/usr/bin/env python3
"""Account for PDF rules which character-only comparisons cannot see.

Rules beside mathematics must belong to an explicit source-checked
transcription. Field-diagram boundaries remain in the source illustration.
"""
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
import pymupdf as fitz
from reviewed_math import entries,qam_latex

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/full-audit'
# Inspected field-diagram boundaries, rather than mathematical operators.
# Do not classify new unrendered mathematics as an illustration just because
# the DOM happens to contain no KaTeX nodes.
DIAGRAMS={
    'GBT-46803.1-2025':{16:('前导信号',),17:('前导信号',),18:('前导信号',)},
    'GBT-46803.2-2025':{159:('数据类型索引:0x0133','安全属性'),161:('安全属性',),167:('数据类型索引:0x0139',),172:('数据类型索引:0x0139','数据类型索引:0x013A'),182:('数据类型索引:0x0149',)},
    'GBT-48336.304-2026':{16:('在融合系统中',)},
    'GBT-48336.402-2026':{16:('合作设备集合标识随机数',)},
}


def source_nodes(source,dom):
    """Match source blocks, including reviewed multi-item regions and fragments."""
    nodes={}
    blocks=[b for b in source['blocks'] if b.get('rendered',True)]
    for file,chapter in dom.items():
        selected=[b for b in blocks if b['file']==file and not b.get('continuation_of')]
        multi=any(b.get('render_counts') for b in selected)
        for kind,actual in chapter['blocks'].items():
            if multi and kind in ('paragraph','list_item'):continue
            expected=sorted((b for b in selected if b['kind']==kind),key=lambda b:(b['page'],b['bbox'][1]))
            if len(expected)!=len(actual):raise ValueError('Block count changed: '+file+' '+kind)
            for b,node in zip(expected,actual):nodes[b['page'],tuple(b['line_ids'])]=node
        if multi:
            cursor=0
            for b in sorted((b for b in selected if b['kind'] in ('paragraph','list_item')),key=lambda b:(b['page'],b['bbox'][1])):
                count=sum(b.get('render_counts',{}).values()) or 1
                children=chapter['paragraph_list_flow'][cursor:cursor+count];cursor+=count
                nodes[b['page'],tuple(b['line_ids'])]={'math':[t for n in children for t in n['math']]}
            if cursor!=len(chapter['paragraph_list_flow']):raise ValueError('Unassigned flow: '+file)
    by_line={(b['page'],li):b for b in blocks for li in b['line_ids']}
    by_key={(b['page'],tuple(b['line_ids'])):b for b in blocks}
    for b in blocks:
        if b['kind']=='math_fragment':
            target=by_line[b['page'],b['math_fragment_of']]
            nodes[b['page'],tuple(b['line_ids'])]=nodes[target['page'],tuple(target['line_ids'])]
        elif b.get('continuation_of'):
            target=b['continuation_of']
            while by_key[target['page'],tuple(target['line_ids'])].get('continuation_of'):target=by_key[target['page'],tuple(target['line_ids'])]['continuation_of']
            nodes[b['page'],tuple(b['line_ids'])]=nodes[target['page'],tuple(target['line_ids'])]
    return nodes


def transcription_matches(entry,node):
    if entry.get('mode') in ('algorithm','code'):return True
    expected=[entry['latex']] if entry.get('latex') else [qam_latex(*entry['qam'])] if entry.get('qam') else re.findall(r'\$([^$\n]+)\$',entry.get('markup',''))
    normalize=lambda s:re.sub(r'\s+',' ',re.sub(r'\\tag\{[^}]+\}','',s)).strip()
    actual=[normalize(t) for t in node.get('math',[])]
    return bool(expected) and all(normalize(t) in actual for t in expected)


def main():
    mp=ROOT/'metadata/reading-manifest.json';manifest=json.loads(mp.read_text())
    records=[];issues=[]
    for doc in manifest['documents']:
        code=doc['code'];h=doc['sha256']
        pdf=fitz.open((Path(os.environ.get('SPARKLINK_LFS_STORAGE','/private/tmp/sparklink-lfs-storage'))/'objects')/h[:2]/h[2:4]/h)
        source=json.loads((OUT/'source'/(code+'.json')).read_text())
        dom={c['path']:c for c in json.loads((OUT/'dom'/(code+'.json')).read_text())}
        nodes=source_nodes(source,dom)
        by_page=defaultdict(list)
        for b in source['blocks']:
            if b.get('rendered',True):by_page[b['page']].append(b)
        for pn,page in enumerate(pdf,1):
            found={}
            for drawing in page.get_drawings():
                for item in drawing['items']:
                    if item[0]!='l':continue
                    a,b=item[1:];vertical=abs(a.x-b.x)<.15 and 4<abs(a.y-b.y)<31
                    horizontal=abs(a.y-b.y)<.15 and 4<abs(a.x-b.x)<90
                    if not (vertical or horizontal):continue
                    x,y=(a.x+b.x)/2,(a.y+b.y)/2
                    for block in by_page[pn]:
                        x0,y0,x1,y1=block['bbox']
                        if x0-3<=x<=x1+3 and y0-3<=y<=y1+3:
                            key=tuple(block['line_ids'])
                            row=found.setdefault(key,{'block':block,'rules':[]})
                            row['rules'].append([a.x,a.y,b.x,b.y]);break
            for row in found.values():
                block=row['block'];file=block['file'];kind=block['kind']
                node=nodes.get((block['page'],tuple(block['line_ids'])),{})
                rules=row['rules'];reviewed=[e for e in entries() if e['code']==code and e['page']==pn and any(e['bbox'][0]-2<=(r[0]+r[2])/2<=e['bbox'][2]+2 and e['bbox'][1]-2<=(r[1]+r[3])/2<=e['bbox'][3]+2 for r in rules)]
                # Reviewed multi-item regions can render several list nodes;
                # their complete content is checked by check_corpus_content.
                verified=[e for e in reviewed if transcription_matches(e,node)]
                # Match the same 3 pt margin used to collect source rules;
                # a bracket's rule can extend below the last character box.
                covered=lambda r:any(e['bbox'][0]-3<=(r[0]+r[2])/2<=e['bbox'][2]+3 and e['bbox'][1]-3<=(r[1]+r[3])/2<=e['bbox'][3]+3 for e in verified)
                explicit=all(covered(r) for r in rules)
                prefixes=DIAGRAMS.get(code,{}).get(pn,())
                field_diagram=bool(prefixes and block['source_text'].startswith(prefixes))
                status='source-reviewed-mathematics' if explicit else 'illustration-boundaries' if field_diagram else 'unaccounted'
                record={'code':code,'page':pn,'file':file,'line_ids':block['line_ids'],'source_pdf_sha256':h,'source_text_sha256':hashlib.sha256(block['source_text'].encode()).hexdigest(),'rules':rules,'status':status,'native_tex_sha256':hashlib.sha256(json.dumps(node.get('math',[]),ensure_ascii=False).encode()).hexdigest()}
                records.append(record)
                if status=='unaccounted':issues.append(record)
    report={'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'documents':len(manifest['documents']),'scope':'Straight PDF rules overlapping text/formula block bounds: vertical 4–31 pt, horizontal 4–90 pt, 3 pt margin. Mathematical rules are covered by explicit source-reviewed transcriptions; illustration borders remain in original figures. This complements glyph/script and pixel checks.','blocks':len(records),'rules':sum(len(r['rules']) for r in records),'issues':issues,'results':records}
    (OUT/'vector-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Vector-rule blocks',len(records),'rules',report['rules'],'issues',len(issues))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
