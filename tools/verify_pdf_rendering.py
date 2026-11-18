#!/usr/bin/env python3
"""Compare browser-rendered source pages with independent PDF rasterization."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lfs-storage',type=Path,default=Path('/private/tmp/sparklink-lfs-storage'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'metadata/reading-manifest.json').read_text())
    checks=json.loads((root/'metadata/browser-check.json').read_text())
    digest=hashlib.sha256((root/'metadata/reading-manifest.json').read_bytes()).hexdigest()
    if checks.get('manifest_sha256')!=digest:raise SystemExit('Run browser checks for the current manifest first.')
    documents={d['code']:d for d in manifest['documents']}
    results=[]
    for sample in checks['samples']:
        doc=documents[sample['code']]
        h=doc['sha256']
        pdf=args.lfs_storage/'objects'/h[:2]/h[2:4]/h
        with pymupdf.open(pdf) as original:
            pix=original[sample['page']-1].get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False)
        reference=Image.frombytes('RGB',(pix.width,pix.height),pix.samples).convert('L')
        browser=Image.open(root/sample['path']).convert('L')
        if reference.size != browser.size:
            results.append({**sample,'pass':False,'reason':'different raster dimensions','pdf_size':reference.size,'html_size':browser.size})
            continue
        a=np.asarray(reference,dtype=np.int16)
        b=np.asarray(browser,dtype=np.int16)
        mae=float(np.abs(a-b).mean())
        ink_a=a<180
        ink_b=b<180
        # PDF and Chromium use different grayscale antialiasing for hairlines.
        # Match core ink (<180) against nearby antialiased ink (<200); absent
        # glyphs and geometry still have no matching pixels.
        near_a=np.asarray(Image.fromarray(((a<200)*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)))>0
        near_b=np.asarray(Image.fromarray(((b<200)*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)))>0
        recall=float((ink_a & near_b).sum()/ink_a.sum()) if ink_a.any() else 1.0
        precision=float((ink_b & near_a).sum()/ink_b.sum()) if ink_b.any() else 1.0
        passed=mae<=8.0 and recall>=0.96 and precision>=0.96
        results.append({**sample,'pass':passed,'mean_absolute_gray_error':round(mae,5),
                        'ink_recall_with_1px_tolerance':round(recall,6),'ink_precision_with_1px_tolerance':round(precision,6)})
    report={'manifest_sha256':digest,'samples':len(results),'passed':sum(r['pass'] for r in results),'failed':sum(not r['pass'] for r in results),
            'method':'Browser SVG canvas at 144 dpi vs fresh PDF rasterization; core ink <180 matched to antialiased ink <200 within 1 pixel; ink recall/precision >= 96%; mean gray error <= 8/255',
            'results':results}
    (root/'metadata/pdf-html-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))
    for row in results:
        if not row['pass']:print(json.dumps(row,ensure_ascii=False))
    raise SystemExit(1 if report['failed'] else 0)


if __name__=='__main__':main()
