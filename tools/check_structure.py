#!/usr/bin/env python3
"""Check every source page and paragraph, not only a few generated examples."""
import argparse
import hashlib
import html
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
import pymupdf
from repair_myst import pdf_lines
from recover_201 import load_map,load_ocr,fallback_lines

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lfs-storage',type=Path,default=Path('/private/tmp/sparklink-lfs-storage'))
    args=parser.parse_args()
    manifest_path=ROOT/'metadata/reading-manifest.json'
    manifest=json.loads(manifest_path.read_text());issues=[];results=[]
    reviewed_tables={t['id']:t for t in json.loads((ROOT/'metadata/reviewed-tables.json').read_text())['tables']}
    for doc in manifest['documents']:
        local=[];code=doc['code'];covered=set();slugs=[];assets=set()
        headings=[]
        data=json.loads((ROOT/doc['paragraph_ledger']).read_text())
        keys=Counter((p['page'],i) for p in data['blocks'] for i in p['line_ids'])
        duplicates=[k for k,n in keys.items() if n>1]
        if duplicates:local.append({'duplicate_source_lines':duplicates})
        regions=defaultdict(list)
        for r in data['regions']:regions[r['page']].append(r['bbox'])
        for chapter in doc['chapters']:
            file=ROOT/chapter['path'];text=file.read_text();slugs.append(chapter['slug'])
            covered.update(a['page'] for a in doc['page_assets'])
            native=text
            if re.search(r'tab-item}|pdf-facsimile|PDF 第|封面与目录|^##? 目录\s*$',native,re.M):local.append({'paper_layout_in_web_page':chapter['path']})
            if re.search(r'^:{3,}[ \t]+:{3,}',native,re.M):local.append({'joined_directive_fences':chapter['path']})
            headings+=re.findall(r'^#{1,6} (.+)$',text,re.M)
            if len(re.findall(r'^# ',text,re.M))!=1:local.append({'invalid_document_heading':chapter['path']})
            if re.search(r'p\d{4}-(?:inline-\d{3}-\d{2}|equation-\d{3}|t\d{2}-cell-\d{3}-\d{3})\.png',native):
                local.append({'formula_bitmap':chapter['path']})
            if '□' in native:local.append({'unresolved_glyph':chapter['path']})
            if re.search('[À-ÖØ-Þà-öø-ÿ\ue000-\uf8ff\U000f0000-\U0010fffd]',native):local.append({'unconverted_pdf_symbol':chapter['path']})
            if code=='GBT-48336.201-2026':
                for seq in re.finditer(r'Iseq\[(\d)\]\s*=\s*\{([^}]+)\}',native,re.S):
                    numbers=[int(x) for x in re.findall(r'\d+',seq[2])]
                    if len(numbers)!=62 or set(numbers)!=set(range(62)):local.append({'invalid_interleaver_sequence':seq[1]})
            previous=1
            for h in re.findall(r'^(#{1,6}) .+',text,re.M):
                depth=len(h)
                if depth>previous+1:local.append({'skipped_heading_depth':chapter['path']})
                previous=depth
            refs=re.findall(r'^```\{image\}\s+(.+)$|<img[^>]+src="([^"]+)"',text,re.M)
            for parts in refs:
                raw=html.unescape(next(x for x in parts if x))
                resource=(file.parent/raw).resolve();assets.add(str(resource))
                if not resource.is_file():local.append({'missing_asset':str(resource)})
        if covered!=set(range(1,doc['pages']+1)):local.append({'missing_pages':sorted(set(range(1,doc['pages']+1))-covered)})
        if len(set(slugs))!=len(slugs):local.append('duplicate chapter routes')
        for table in doc['tables']:
            if table.get('missing_glyphs'):local.append({'unassigned_table_glyphs':{'id':table['id'],'glyphs':table['missing_glyphs']}})
            if table.get('geometry_review'):
                review=reviewed_tables[table['geometry_review']]
                if review['source_sha256']!=doc['sha256'] or max(abs(a-b) for a,b in zip(review['bbox'],table['bbox']))>.01 or not (ROOT/review['evidence']).is_file():local.append({'invalid_table_geometry_review':table['id']})
        def normalize(title):return re.sub(r'\\(?=[`*_{}\[\]$<>])|\s','',html.unescape(title)).replace('．','.')
        actual={normalize(h) for h in headings}
        for block in data['blocks']:
            if block.get('rendered',True) and block['kind']=='caption' and re.match(r'^表\s*(?:[A-Z]\s*\.)?\s*\d+',block['source_text']):
                local.append({'unstructured_source_table':{'page':block['page'],'caption':block['source_text']}})
            if block.get('rendered',True):continue
            reason=block.get('omission_reason')
            if reason=='paper-cover-and-print-contents' and block['page']<=4:continue
            if reason=='repeated-paper-heading' and block['kind'] in ('heading','title_fragment') and normalize(block['source_text']) in actual:continue
            local.append({'invalid_source_omission':{'page':block['page'],'kind':block['kind'],'reason':reason,'text':block['source_text']}})
        for item in doc['toc']:
            if item['title']=='封面与目录':continue
            if normalize(item['title']) not in actual:local.append({'missing_toc_heading':item['title']})
        for heading in headings:
            if re.match(r'^\d[\d.]*\.\.',heading):local.append({'malformed_clause_number':heading})
        h=doc['sha256'];source=args.lfs_storage/'objects'/h[:2]/h[2:4]/h
        if hashlib.sha256(source.read_bytes()).hexdigest()!=h:local.append('source SHA-256 mismatch')
        mapping=load_map() if doc['broken_mapping'] else None
        ocr=load_ocr() if mapping else None
        accounted=0;total=0
        with pymupdf.open(source) as pdf:
            if len(pdf)!=doc['pages']:local.append('source page count mismatch')
            for pn,page in enumerate(pdf,1):
                lines=pdf_lines(page,mapping)
                if mapping:lines=fallback_lines(page,lines,ocr.get(pn,[]))
                for i,line in enumerate(lines):
                    text=line['text'];box=line['bbox'];cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
                    if not text.strip():continue
                    if not pymupdf.Rect(box).intersects(page.rect):continue
                    total+=1
                    header=bool(re.match(r'^GB\s*/?\s*T\s*\d',text) and (box[1]<95 or box[1]>page.rect.height-65))
                    footer=bool(re.fullmatch(r'[\dⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+',text) and box[1]>page.rect.height-90)
                    in_region=any(r[0]<=cx<=r[2] and r[1]<=cy<=r[3] for r in regions[pn])
                    if (pn,i) in keys or pn in (3,4) or header or footer or in_region:accounted+=1
                    else:local.append({'unaccounted_source_line':{'page':pn,'line':i,'text':text,'bbox':box}})
        result={'code':code,'chapters':len(slugs),'source_pages':len(covered),'source_lines':total,'accounted_source_lines':accounted,
                'paragraph_blocks':len(data['blocks']),'assets':len(assets),'issues':local}
        results.append(result)
        if local:issues.append(result)
        print(f'{code}: {accounted}/{total} source lines accounted, {len(local)} issues',flush=True)
    report={'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'documents':len(results),
            'chapters':sum(r['chapters'] for r in results),'issues':issues,'results':results}
    (ROOT/'metadata/structure-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(bool(issues))


if __name__=='__main__':main()
