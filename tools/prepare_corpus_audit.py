#!/usr/bin/env python3
"""Independent source material for a full corpus content audit.

Table text comes from raw PDF characters, not the table converter or its
texttrace Unicode. This also catches disagreements between PDF text APIs.
"""
import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import pymupdf as fitz
from recover_201 import load_map,decode_span,load_ocr,fallback_lines
from repair_myst import pdf_lines
from source_semantics import decode as semantic_decode
from pdf_spans import ink_x
from pdf_tables import find_tables

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/full-audit/source'


def raw_glyphs(page,mapping):
    glyphs=[]
    ids={(t['font'],round(o[0],3),round(o[1],3)):gid for t in page.get_texttrace() for u,gid,o,b in t['chars']}
    for block in page.get_text('rawdict',flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']:
        if block['type']!=0:continue
        for line in block['lines']:
            for span in line['spans']:
                for g in span['chars']:
                    char=decode_span({'font':span['font'],'text':g['c']},mapping) if mapping else semantic_decode(span['font'],g['c'])
                    if not char.strip():continue
                    glyphs.append({'c':char,'x':g['origin'][0],'y':g['origin'][1],
                                   'size':span['size'],'bbox':g['bbox'],'font':span['font'],
                                   'ink_x':ink_x(page,span['font'],ids.get((span['font'],round(g['origin'][0],3),round(g['origin'][1],3)),0),g['origin'],span['size'],g['bbox'],char)[0]})
    return glyphs


def cell_lines(glyphs):
    # Keep source character order on each physical baseline. Small scripts
    # remain explicit glyph records for the separate mathematics audit.
    groups=[]
    for g in sorted(glyphs,key=lambda g:(g['y'],g['x'])):
        if groups and abs(g['y']-groups[-1][0]['y'])<2.3:groups[-1].append(g)
        else:groups.append([g])
    return [''.join(g['c'] for g in sorted(row,key=lambda g:g['x'])) for row in groups]


def audit_document(doc,storage):
    h=doc['sha256'];path=Path(storage)/'objects'/h[:2]/h[2:4]/h
    assert hashlib.sha256(path.read_bytes()).hexdigest()==h
    ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text())
    mapping=load_map() if doc['broken_mapping'] else None;ocr=load_ocr() if mapping else None
    by_page=defaultdict(list)
    for table in doc['tables']:by_page[table['page']].append(table)
    blocks_by_page=defaultdict(list)
    for i,b in enumerate(ledger['blocks']):blocks_by_page[b['page']].append((i,b))
    tables=[];source_issues=[];pdf=fitz.open(path);normalized=lambda s:re.sub(r'\s','',s)
    for pn,page in enumerate(pdf,1):
        lines=pdf_lines(page,mapping)
        if mapping:lines=fallback_lines(page,lines,ocr[pn])
        glyphs=raw_glyphs(page,mapping)
        by_font=defaultdict(list)
        for g in glyphs:by_font[g['font'],round(g['y'],1),round(g['size'],1)].append(g)
        for i,b in blocks_by_page[pn]:
            fresh='\n'.join(lines[li]['text'] for li in b['line_ids'])
            if normalized(fresh)!=normalized(b['source_text']):source_issues.append({'block':i,'page':pn,'fresh':fresh,'ledger':b['source_text']})
            b['semantic_source']='\n'.join(''.join(semantic_decode(s['font'],s['text']) for s in lines[li]['spans']) for li in b['line_ids'])
            chosen={}
            for li in b['line_ids']:
                for span in lines[li]['spans']:
                    if '_glyphs' in span:
                        candidates=[{'c':decode_span({'font':span['font'],'text':g['c']},mapping),'x':g['origin'][0],'ink_x':g['bbox'][0],'y':g['origin'][1],'size':span['size'],'font':span['font']} for g in span['_glyphs']]
                    else:
                        candidates=[g for g in by_font[span['font'],round(span['origin'][1],1),round(span['size'],1)] if span['bbox'][0]-1<=g['x']<=span['bbox'][2]+.1]
                    for g in candidates:chosen[g['font'],g['x'],g['y']]=g
            b['source_glyphs']=list(chosen.values())
        if pn not in by_page:continue
        found=find_tables(page,doc['code'])
        for info in by_page[pn]:
            table=min(found,key=lambda t:sum(abs(a-b) for a,b in zip(t.bbox,info['bbox'])))
            assert max(abs(a-b) for a,b in zip(table.bbox,info['bbox']))<.1,(doc['code'],pn)
            boxes=list(dict.fromkeys(tuple(c) for c in table.cells if c))
            cells=[]
            for box in boxes:
                right=box[2]+(.3 if abs(box[2]-table.bbox[2])<.1 else -.3)
                selected=[g for g in glyphs if box[0]-.3<=g['x']<right and box[1]<g['y']-g['size']*.25<box[3]]
                cells.append({'bbox':box,'lines':cell_lines(selected),'glyphs':selected})
            region=next(r for r in ledger['regions'] if r['kind']=='table' and r['page']==pn and r['bbox']==info['bbox'])
            tables.append({**info,'file':region['file'],'source_cells':cells})
    data={'code':doc['code'],'source_sha256':h,'pages':len(pdf),'source_issues':source_issues,'blocks':ledger['blocks'],'tables':tables}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/(doc['code']+'.json')).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
    return {'code':doc['code'],'blocks':len(ledger['blocks']),'tables':len(tables),'cells':sum(len(t['source_cells']) for t in tables),'source_issues':len(source_issues)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--only',help='Standard code substring; preserve other cached source documents')
    parser.add_argument('--lfs-storage',default=os.environ.get('SPARKLINK_LFS_STORAGE','/private/tmp/sparklink-lfs-storage'));args=parser.parse_args()
    manifest=json.loads((ROOT/'metadata/reading-manifest.json').read_text());results=[]
    selected=[d for d in manifest['documents'] if not args.only or any(code in d['code'] for code in args.only.split(','))]
    if not selected:raise ValueError('No matching standard')
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs=[pool.submit(audit_document,d,args.lfs_storage) for d in selected]
        for job in as_completed(jobs):
            result=job.result();results.append(result);print(json.dumps(result),flush=True)
    path=ROOT/'tmp/full-audit/source-preparation.json'
    if args.only and path.exists():
        current={r['code']:r for r in json.loads(path.read_text())};current.update({r['code']:r for r in results});results=list(current.values())
    results.sort(key=lambda r:r['code'])
    path.write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':main()
