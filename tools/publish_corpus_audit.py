#!/usr/bin/env python3
"""Publish only complete, current, zero-issue corpus evidence."""
import hashlib
import json
import shutil
from pathlib import Path
from quality_report import write_report
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/full-audit'


def main():
    data=(ROOT/'metadata/reading-manifest.json').read_bytes();digest=hashlib.sha256(data).hexdigest();manifest=json.loads(data)
    reports={name:json.loads((OUT/(name+'-check.json')).read_text()) for name in ('content','visual','vector')}
    for name,report in reports.items():
        if report['manifest_sha256']!=digest or report['issues']:raise ValueError('Incomplete or stale '+name+' audit')
    for name in ['structure-check','native-math-check','heading-check','browser-check','reader-interactions','web-edition-check','201-content-check','201-rendered-text-check','pdf-html-comparison','reference-scope-check']:
        check=json.loads((ROOT/'metadata'/(name+'.json')).read_text())
        if check['manifest_sha256']!=digest or check.get('issues') or check.get('failed'):raise ValueError('Incomplete or stale '+name)
    if reports['content'].get('reader_sha256')!=hashlib.sha256((ROOT/'_build/html/reader.js').read_bytes()).hexdigest():raise ValueError('Stale reader code evidence')
    chapters=reports['content'].get('chapter_snapshots',[])
    if len(chapters)!=manifest['totals']['chapters']:raise ValueError('Incomplete chapter snapshots')
    for chapter in chapters:
        for path,key in [('file','markdown_sha256'),('html_file','html_sha256')]:
            if hashlib.sha256((ROOT/chapter[path]).read_bytes()).hexdigest()!=chapter[key]:raise ValueError('Stale snapshot: '+chapter[path])
    for name,count in [('cell',reports['content']['cells']),('block',reports['content']['blocks'])]:
        rows=[json.loads(line) for line in (OUT/(name+'-checks.jsonl')).read_text().splitlines()]
        if len(rows)!=count or any(not r['matches'] for r in rows):raise ValueError('Incomplete '+name+' evidence')
    for name in reports:shutil.copyfile(OUT/(name+'-check.json'),ROOT/'metadata'/('corpus-'+name+'-check.json'))
    for name in ('cell','block'):shutil.copyfile(OUT/(name+'-checks.jsonl'),ROOT/'metadata'/('corpus-'+name+'-checks.jsonl'))
    write_report();print('Published current content, cell, block, vector and visual audit evidence')


if __name__=='__main__':main()
