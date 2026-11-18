#!/usr/bin/env python3
"""Check every original-page SVG and extracted figure against the PDF."""
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import pymupdf as fitz
from PIL import Image,ImageFilter
from source_archive import source_path

ROOT=Path(__file__).resolve().parents[1]


def metrics(a,b):
    if a.shape!=b.shape:return {'pass':False,'source_size':list(a.shape),'asset_size':list(b.shape)}
    mae=float(abs(a.astype(float)-b.astype(float)).mean());ia=a<180;ib=b<180
    na=np.asarray(Image.fromarray(((a<200)*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)))>0
    nb=np.asarray(Image.fromarray(((b<200)*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)))>0
    recall=float((ia&nb).sum()/ia.sum()) if ia.any() else 1.0
    precision=float((ib&na).sum()/ib.sum()) if ib.any() else 1.0
    return {'pass':mae<=8 and recall>=.96 and precision>=.96,'mae':round(mae,5),'recall':round(recall,6),'precision':round(precision,6)}


def check_document(doc):
    h=doc['sha256'];pdf=fitz.open((Path(os.environ.get('SPARKLINK_LFS_STORAGE','/private/tmp/sparklink-lfs-storage'))/'objects')/h[:2]/h[2:4]/h)
    ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text());pages=[];figures=[]
    for info in doc['page_assets']:
        pn=info['page'];p=pdf[pn-1].get_pixmap(matrix=fitz.Matrix(2,2),colorspace=fitz.csGRAY,alpha=False)
        with fitz.open(source_path(info['asset'])) as svg:q=svg[0].get_pixmap(matrix=fitz.Matrix(2,2),colorspace=fitz.csGRAY,alpha=False)
        a=np.frombuffer(p.samples,dtype=np.uint8).reshape(p.height,p.width);b=np.frombuffer(q.samples,dtype=np.uint8).reshape(q.height,q.width)
        pages.append({'page':pn,**metrics(a,b)})
    seen=set()
    for r in ledger['regions']:
        if not r.get('rendered',True):continue
        if not r.get('asset') or r['asset'] in seen:continue
        seen.add(r['asset']);page=pdf[r['page']-1];box=(fitz.Rect(r['bbox'])+(-2,-2,2,2))&page.rect
        # Render only the recorded region; retain the exact source rounding.
        p=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=box,alpha=False)
        with Image.open(ROOT/r['asset']) as image:a=np.array(image.convert('RGB'))
        b=np.frombuffer(p.samples,dtype=np.uint8).reshape(p.height,p.width,p.n)
        same=a.shape==b.shape and np.array_equal(a,b)
        figures.append({'page':r['page'],'asset':r['asset'],'pass':bool(same)})
    result={'code':doc['code'],'pages':pages,'figures':figures};print(doc['code'],len(pages),'pages',len(figures),'figures',sum(not r['pass'] for r in pages+figures),'issues',flush=True)
    return result


def main():
    path=ROOT/'metadata/reading-manifest.json';manifest=json.loads(path.read_text());results=[]
    with ProcessPoolExecutor(max_workers=3) as pool:
        for job in as_completed([pool.submit(check_document,d) for d in manifest['documents']]):results.append(job.result())
    issues=[{'code':d['code'],'kind':kind,**r} for d in results for kind in ('pages','figures') for r in d[kind] if not r['pass']]
    report={'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'method':'All original SVG pages at 144 dpi against fresh PDF rendering; extracted PNG figures pixel-exact against original regions. Browser renderer is checked separately.','pages':sum(len(d['pages']) for d in results),'figures':sum(len(d['figures']) for d in results),'issues':issues,'results':results}
    (ROOT/'tmp/full-audit/visual-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Visual issues',len(issues));raise SystemExit(1 if issues else 0)


if __name__=='__main__':main()
