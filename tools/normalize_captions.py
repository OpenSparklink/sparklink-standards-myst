"""Keep the source figure/table number separate from a numeric title."""
import html
import json
import re
from pathlib import Path


def format_caption(rich,source):
    match=re.match(r'^\s*([图表])\s*((?:[A-Z]\s*\.\s*)?\d+)',source)
    if not match:return rich
    number=re.sub(r'\s+','',match[2]);label=match[1]+' '+number
    plain=re.sub(r'</?strong>','',rich)
    pattern=r'^\s*'+r'\s*'.join(re.escape(c) for c in match[1]+number)
    prefix=re.match(pattern,plain)
    if not prefix:return rich
    return html.escape(label)+'　'+plain[prefix.end():].lstrip()


def normalize(text,filename,tables,blocks,regions):
    locations={(r['page'],tuple(r['bbox'])) for r in regions if r['kind']=='table' and r['file']==filename}
    selected=sorted((t for t in tables if (t['page'],tuple(t['bbox'])) in locations),key=lambda t:(t['page'],t['bbox'][1]))
    figures=sorted((b for b in blocks if b['kind']=='caption' and b['file']==filename),key=lambda b:(b['page'],b['bbox'][1]))
    for cls,items in [('standard-table-caption',selected),('standard-caption',figures)]:
        pattern=r'(:class: '+cls+r'\n\n<p>)(.*?)(</p>)'
        matches=list(re.finditer(pattern,text,re.S))
        if len(matches)!=len(items):raise ValueError(f'Caption coverage mismatch: {filename} {cls} {len(matches)}/{len(items)}')
        for match,item in reversed(list(zip(matches,items))):
            source=item.get('caption',item.get('source_text',''))
            text=text[:match.start(2)]+format_caption(match[2],source)+text[match.end(2):]
    return text


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'metadata/reading-manifest.json').read_text())
    changed=0
    for doc in manifest['documents']:
        ledger=json.loads((root/doc['paragraph_ledger']).read_text())
        for chapter in doc['chapters']:
            file=root/chapter['path'];old=file.read_text()
            new=normalize(old,chapter['path'],doc['tables'],ledger['blocks'],ledger['regions'])
            if new!=old:file.write_text(new);changed+=1
    print(f'Normalized captions in {changed} chapter files.')
