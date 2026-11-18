#!/usr/bin/env python3
"""Close each restored paragraph against source lines and verified glyphs."""
import hashlib
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
import pymupdf as fitz
from repair_myst import pdf_lines
from recover_201 import load_map,load_ocr,fallback_lines

ROOT=Path(__file__).resolve().parents[1]
CODE='GBT-48336.201-2026'


def main():
    mp=ROOT/'metadata/reading-manifest.json';manifest=json.loads(mp.read_text());doc=next(d for d in manifest['documents'] if d['code']==CODE)
    proof=json.loads((ROOT/'metadata/201-verified-glyphs.json').read_text());h=doc['sha256'];pdf=fitz.open(Path('/private/tmp/sparklink-lfs-storage/objects')/h[:2]/h[2:4]/h)
    assert proof['source_sha256']==h
    issues=[];pages={};mapping=load_map();ocr=load_ocr();page_rows=[];observed=Counter()
    verified={g['key']:g for g in proof['glyphs']}
    for pn,page in enumerate(pdf,1):
        lines=fallback_lines(page,pdf_lines(page,mapping),ocr[pn]);pages[pn]=lines
        fallbacks=[i for i,l in enumerate(lines) if l.get('ocr') or l.get('character_ocr') or '□' in l['text']]
        if fallbacks:issues.append({'page':pn,'unverified_character_recovery':fallbacks})
        for trace in page.get_texttrace():
            for unicode,gid,origin,bbox in trace['chars']:
                if unicode<=32 or bbox[0]>page.rect.width or bbox[1]>page.rect.height:continue
                key=trace['font']+'\t'+chr(unicode);observed[key]+=1
                if key not in verified or verified[key]['status']!='verified' or mapping.get(key)!=verified[key]['character']:
                    issues.append({'page':pn,'unverified_glyph':key})
        page_rows.append({'page':pn,'source_lines':len(lines),'character_ocr_fallbacks':len(fallbacks)})
    ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text());blocks=[]
    normalize=lambda text:re.sub(r'\s','',text)
    for i,block in enumerate(ledger['blocks']):
        source='\n'.join(pages[block['page']][li]['text'] for li in block['line_ids'])
        same=normalize(source)==normalize(block['source_text'])
        if not same:issues.append({'block':i,'page':block['page'],'source_line_text_mismatch':{'fresh':source,'ledger':block['source_text']}})
        if block.get('reading_order_text'):
            han=lambda s:Counter(re.findall(r'[\u3400-\u9fff]',s))
            if han(source)!=han(block['reading_order_text']):issues.append({'block':i,'reading_order_changed_source_characters':True})
        if block['kind']=='equation' and not block.get('reviewed_math'):issues.append({'block':i,'unreviewed_display_equation':True})
        blocks.append({'id':i,'page':block['page'],'kind':block['kind'],'file':block['file'],'source_lines':block['line_ids'],'source_text_sha256':hashlib.sha256(normalize(source).encode()).hexdigest(),'source_text_matches':same,'reviewed_region':bool(block.get('reviewed_math'))})
    tags=Counter()
    for chapter in doc['chapters']:
        native=(ROOT/chapter['path']).read_text()
        tags.update(int(n) for n in re.findall(r'\\tag\{(\d+)\}',native))
        if re.search(r'p\d{4}-(?:inline-|equation-|t\d+-cell-)',native):issues.append({'formula_bitmap':chapter['path']})
    if tags!=Counter(range(1,80)):issues.append({'numbered_formulas':dict(tags),'expected':'1 through 79, exactly once'})
    old=json.loads((ROOT/'metadata/201-font-map.json').read_text())
    if old['review']:issues.append({'remaining_ocr_review_entries':len(old['review'])})
    if proof['unresolved']:issues.append({'remaining_glyph_review':proof['unresolved']})
    if len(observed)!=proof['glyph_keys'] or sum(observed.values())!=proof['occurrences']:issues.append('Source glyph coverage changed')
    report={'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'source_sha256':h,'documents':1,'pages':len(pages),'paragraph_blocks':len(blocks),'verified_glyph_keys':len(observed),'verified_glyph_occurrences':sum(observed.values()),'character_ocr_fallbacks':sum(r['character_ocr_fallbacks'] for r in page_rows),'numbered_formulas':len(tags),'reviewed_display_equations':sum(b['kind']=='equation' for b in blocks),'remaining_review_items':len(old['review'])+len(proof['unresolved']),'issues':issues,'page_results':page_rows,'blocks':blocks}
    (ROOT/'metadata/201-content-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['pages','paragraph_blocks','verified_glyph_keys','verified_glyph_occurrences','character_ocr_fallbacks','numbered_formulas','remaining_review_items']}|{'issues':len(issues)}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
