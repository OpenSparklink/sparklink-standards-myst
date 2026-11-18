#!/usr/bin/env python3
"""Resolve blank-page comparisons and independently check browser evidence."""
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image
import pymupdf as fitz
from check_source_visuals import metrics,ROOT
from source_archive import source_path


def main():
    path=ROOT/'tmp/full-audit/visual-check.json';report=json.loads(path.read_text())
    docs={d['code']:d for d in json.loads((ROOT/'metadata/reading-manifest.json').read_text())['documents']}
    browsers=0;blanks=0
    for result in report['results']:
        doc=docs[result['code']];h=doc['sha256'];pdf=fitz.open((Path(os.environ.get('SPARKLINK_LFS_STORAGE','/private/tmp/sparklink-lfs-storage'))/'objects')/h[:2]/h[2:4]/h)
        result['source_sha256']=h
        for row in result['pages']:
            if row['pass']:continue
            pn=row['page'];p=pdf[pn-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            a=np.asarray(Image.frombytes('RGB',(p.width,p.height),p.samples).convert('L'))
            if row.get('mae')==0 and row.get('recall')==0 and row.get('precision')==0:
                with fitz.open(source_path(doc['page_assets'][pn-1]['asset'])) as svg:q=svg[0].get_pixmap(matrix=fitz.Matrix(2,2),colorspace=fitz.csGRAY,alpha=False)
                b=np.frombuffer(q.samples,dtype=np.uint8).reshape(q.height,q.width)
                fresh=metrics(a,b);assert not (a<180).any() and not (b<180).any();row.update(fresh,verification='empty-ink-both-renderings');blanks+=1
            else:
                png=ROOT/f'tmp/full-audit/svg-browser/{doc["code"]}-p{pn}.png'
                b=np.asarray(Image.open(png).convert('L'));fresh=metrics(a,b)
                old={k:row[k] for k in ('pass','mae','recall','precision')};row.update(fresh,verification='chromium',secondary_svg_renderer=old);browsers+=1
    report['issues']=[{'code':d['code'],'kind':kind,**r} for d in report['results'] for kind in ('pages','figures') for r in d[kind] if not r['pass']]
    report['browser_resolutions']=browsers;report['blank_pages_checked']=blanks
    report['method']='All 1755 page SVGs compared to fresh PDF at 144 dpi. Secondary SVG renderer discrepancies resolved in Chromium; blank pages explicitly checked for absent ink. All extracted figures compared pixel-exact to source crops.'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Browser resolutions',browsers,'blank pages',blanks,'remaining issues',len(report['issues']))
    if report['issues']:print(report['issues']);raise SystemExit(1)


if __name__=='__main__':main()
