"""Repair real paragraph splits at obsolete PDF-chunk boundaries."""
import json,re
from pathlib import Path
from paragraphs import text_join
ROOT=Path(__file__).resolve().parents[1]
PARAGRAPH=re.compile(r':::\{div\}\n:class: standard-paragraph\s*\n\s*<p>(.*?)</p>\s*\n:::',re.S)
LIST_ITEM=re.compile(r'<li><p>(.*?)</p>',re.S)


def join_paragraphs(doc):
    if doc.get('web_continuations')==1:return
    path=ROOT/doc['paragraph_ledger'];ledger=json.loads(path.read_text());blocks=ledger['blocks'];active=sorted((b for b in blocks if b.get('rendered',True) and b['kind'] not in ('heading','title_fragment','math_fragment')),key=lambda b:(b['page'],b['bbox'][1]));by_key={(b['page'],tuple(b['line_ids'])):b for b in blocks};joined=[]
    for left,right in zip(active,active[1:]):
        if left['kind'] not in ('paragraph','list_item') or right['kind']!='paragraph' or right.get('continuation_of'):continue
        if left['file']!=right['file'] or left.get('source_file')==right.get('source_file') or right['page']!=left['page']+1:continue
        # These are incomplete Chinese words/clauses, not a completed code or
        # primitive signature followed by a new paragraph.
        if not re.search(r'[\u3400-\u9fff]$',left['source_text'].rstrip()):continue
        first=left
        while first.get('continuation_of'):
            target=first['continuation_of'];first=by_key[target['page'],tuple(target['line_ids'])]
        md=ROOT/right['file'];text=md.read_text();p_matches=list(PARAGRAPH.finditer(text));l_matches=list(LIST_ITEM.finditer(text))
        p_sources=sorted((b for b in blocks if b['file']==right['file'] and b['kind']=='paragraph' and b.get('rendered',True) and not b.get('continuation_of')),key=lambda b:(b['page'],b['bbox'][1]))
        l_sources=sorted((b for b in blocks if b['file']==right['file'] and b['kind']=='list_item' and b.get('rendered',True) and not b.get('continuation_of')),key=lambda b:(b['page'],b['bbox'][1]))
        if len(p_sources)!=len(p_matches):raise ValueError(('Paragraph mapping',doc['code'],right['page'],len(p_sources),len(p_matches)))
        if first['kind']=='list_item' and len(l_sources)!=len(l_matches):raise ValueError(('List mapping',doc['code'],right['page']))
        pm=p_matches[p_sources.index(right)]
        lm=p_matches[p_sources.index(first)] if first['kind']=='paragraph' else l_matches[l_sources.index(first)]
        gap=text[lm.end():pm.start()]
        if not re.fullmatch(r'(?:\s|</li>|</ul>|</ol>|:::)*',gap):raise ValueError(('Intervening content at continuation',doc['code'],right['page'],gap[:100]))
        body=text_join([lm[1],pm[1]])
        text=text[:pm.start()]+text[pm.end():]
        text=text[:lm.start(1)]+body+text[lm.end(1):]
        md.write_text(text)
        right['continuation_of']={'page':first['page'],'line_ids':first['line_ids']};right['joined_chunk_boundary']=True;first['continues_on_page']=right['page']
        joined.append({'page':right['page'],'line_ids':right['line_ids'],'target_page':first['page'],'target_lines':first['line_ids']})
    path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n');doc['joined_chunk_paragraphs']=joined;doc['web_continuations']=1
    from web_edition import recalculate
    recalculate(doc,ledger)
