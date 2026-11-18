#!/usr/bin/env python3
"""Prepare source crops / compose evidence for repaired drawn mathematics."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import pymupdf as fitz
from PIL import Image,ImageDraw
from reviewed_math import entries
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'metadata/review/corpus'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compose',action='store_true');args=parser.parse_args()
    path=OUT/'repaired-math.json'
    if args.compose:
        packet=json.loads(path.read_text())
        for row in packet['samples']:
            images=[Image.open(ROOT/row[k]).convert('RGB') for k in ('source_crop','html_crop')]
            for im in images:im.thumbnail((1150,1000))
            canvas=Image.new('RGB',(1180,sum(im.height+40 for im in images)+25),'white');draw=ImageDraw.Draw(canvas);y=10
            for label,im in zip(['Source PDF','Actual HTML'],images):
                draw.text((14,y),row['code']+' | PDF '+str(row['page'])+' | '+label,fill='black');canvas.paste(im,(14,y+24));y+=im.height+40
            target=OUT/(row['id']+'-pair.png');canvas.save(target);row['evidence']=str(target.relative_to(ROOT))
        path.write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n');print('Composed',len(packet['samples']),'source / actual HTML pairs');return
    mp=ROOT/'metadata/reading-manifest.json';manifest=json.loads(mp.read_text());docs={d['code']:d for d in manifest['documents']};samples=[]
    for entry in entries():
        selected=(entry['code']=='GBT-48336.201-2026' and entry['page'] in [53,54,66,75,92,297]) or (entry['code']=='GBT-46803.1-2025' and entry['page']==54)
        if not selected or 'markup' not in entry:continue
        # Only the new complete paragraphs, not pre-existing rate-matching lists.
        if entry['page']==54 and entry['code']=='GBT-46803.1-2025' and entry['bbox'][1]<570:continue
        if entry['page']==92 and entry['bbox'][1]>500:continue
        d=docs[entry['code']];source=json.loads((ROOT/'tmp/full-audit/source'/(d['code']+'.json')).read_text())
        b=next(b for b in source['blocks'] if b['page']==entry['page'] and b['bbox']==entry['bbox'])
        candidates=sorted((v for v in source['blocks'] if v['file']==b['file'] and v['kind']==b['kind'] and not v.get('continuation_of')),key=lambda v:(v['page'],v['bbox'][1]))
        chapter=next(c for c in d['chapters'] if c['path']==b['file']);h=d['sha256'];pdf=fitz.open(Path(os.environ.get('SPARKLINK_LFS_STORAGE','/private/tmp/sparklink-lfs-storage'))/'objects'/h[:2]/h[2:4]/h)
        identifier=d['code']+'-p'+str(b['page'])+'-'+str(len(samples)+1)
        crop=OUT/(identifier+'-source.png');pdf[b['page']-1].get_pixmap(matrix=fitz.Matrix(2.5,2.5),clip=(fitz.Rect(b['bbox'])+(-2,-2,2,2))&pdf[b['page']-1].rect).save(crop)
        samples.append({'id':identifier,'code':d['code'],'page':b['page'],'bbox':b['bbox'],'slug':chapter['slug'],'kind':b['kind'],'node_index':candidates.index(b),'source_pdf_sha256':h,'markdown_sha256':hashlib.sha256((ROOT/b['file']).read_bytes()).hexdigest(),'source_crop':str(crop.relative_to(ROOT)),'html_crop':str((OUT/(identifier+'-html.png')).relative_to(ROOT))})
    path.write_text(json.dumps({'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'samples':samples},ensure_ascii=False,indent=2)+'\n');print('Prepared',len(samples),'source crops')


if __name__=='__main__':main()
