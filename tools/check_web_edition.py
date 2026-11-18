#!/usr/bin/env python3
"""Reject paper artifacts and verify every scoped web reference target."""
import hashlib,json,re,os
from pathlib import Path
from source_archive import source_path
ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('BASE_URL','').rstrip('/')


def main():
    mp=ROOT/'metadata/reading-manifest.json';manifest=json.loads(mp.read_text());index=json.loads((ROOT/'metadata/web-references.json').read_text());issues=[];pages=references=targets=0
    source_flags=re.compile(r'tab-item}|tab-set}|pdf-facsimile|PDF\s*第|封面与目录|^#{1,6}\s*目录\s*$|ICS\s*35|CCS\s*L\s*79|[\u0590-\u08ff\u0e00-\u0e7f\u10a0-\u10ff\ue000-\uf8ff\U000f0000-\U0010fffd]|[\x00-\x08\x0b\x0c\x0e-\x1f]',re.M)
    all_routes={c['slug'] for d in manifest['documents'] for c in d['chapters']}
    caches={d['code']:json.loads((ROOT/'tmp/full-audit/dom'/(d['code']+'.json')).read_text()) for d in manifest['documents']}
    global_routes={c['slug']:c for cache in caches.values() for c in cache}
    for doc in manifest['documents']:
        cache=caches[doc['code']];snapshots={c['path']:c for c in cache};by_route={c['slug']:c for c in cache}
        for chapter in doc['chapters']:
            pages+=1;path=ROOT/chapter['path'];text=path.read_text();flags=source_flags.findall(text)
            if flags:issues.append({'file':chapter['path'],'paper_artifacts':flags[:8]})
            snapshot=snapshots.get(chapter['path'])
            if not snapshot:issues.append({'file':chapter['path'],'type':'missing_html_snapshot'});continue
            if hashlib.sha256(path.read_bytes()).hexdigest()!=snapshot['markdown_sha256']:issues.append({'file':chapter['path'],'type':'stale_snapshot'})
            for url in snapshot.get('references',[]):
                references+=1;route,sep,anchor=url.removeprefix(BASE).strip('/').partition('/#');target=global_routes.get(route)
                if not sep or not target or anchor not in target.get('ids',[]):issues.append({'file':chapter['path'],'invalid_cross_reference':url})
        ref_doc=next(d for d in index['documents'] if d['code']==doc['code'])
        for key,target in ref_doc['targets'].items():
            targets+=1;actual=by_route.get(target['route'])
            if not actual or target['anchor'] not in actual.get('ids',[]):issues.append({'code':doc['code'],'target':key,'url':target['url'],'type':'missing_reference_target'})
        for route in doc['legacy_routes']:
            if route['from'] in all_routes:issues.append({'route':route,'type':'route_collision'})
            alias=ROOT/'_build/html'/route['from']/'index.html';target=ROOT/'_build/html'/route['to']/'index.html'
            if not alias.exists() or not target.exists() or 'name="robots" content="noindex"' not in alias.read_text():issues.append({'route':route,'type':'invalid_legacy_redirect'})
    published_files=[p for p in (ROOT/'_build/html').rglob('*') if p.is_file()]
    archived_pages=[p for p in published_files if re.search(r'page-\d{4}',p.name)]
    if archived_pages:issues.append({'published_original_pages':[str(p.relative_to(ROOT/'_build/html')) for p in archived_pages[:10]]})
    omitted_hashes=set()
    for doc in manifest['documents']:
        ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text())
        for region in ledger['regions']:
            if region.get('rendered',True) or not region.get('asset'):continue
            try:omitted_hashes.add(hashlib.sha256(source_path(region['asset']).read_bytes()).hexdigest())
            except FileNotFoundError:pass
    for path in published_files:
        if path.suffix=='.png' and (re.match(r'p000[1-4]-figure-',path.name) or hashlib.sha256(path.read_bytes()).hexdigest() in omitted_hashes):issues.append({'published_cover_logo':str(path.relative_to(ROOT/'_build/html'))})
        if re.search(r'p\d{4}-(?:inline-\d|equation-\d|t\d+-cell-)',path.name):issues.append({'published_math_bitmap':str(path.relative_to(ROOT/'_build/html'))})
    report={'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'documents':len(manifest['documents']),'pages':pages,'targets':targets,'references':references,'legacy_redirects':sum(len(d['legacy_routes']) for d in manifest['documents']),'joined_table_parts':manifest['totals']['joined_table_parts'],'deduplicated_header_rows':manifest['totals']['deduplicated_header_rows'],'issues':issues}
    (ROOT/'metadata/web-edition-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='issues'}),'issues',len(issues))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
