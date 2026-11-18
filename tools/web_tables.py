"""Join adjacent printed continuation tables, retaining source-cell mappings."""
import html
from html.parser import HTMLParser
import re
from pathlib import Path
import json
import unicodedata
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
BLOCK=re.compile(r'^::::\{div\}\n:class: table-scroll\s*\n.*?^::::\s*$',re.M|re.S)
ROWS=re.compile(r'<tr>.*?</tr>',re.S)


class Cells(HTMLParser):
    def __init__(self):super().__init__();self.cells=[];self.active=None
    def handle_starttag(self,tag,attrs):
        if tag in ('td','th'):
            a=dict(attrs);self.active={'tag':tag,'rowspan':int(a.get('rowspan',1)),'colspan':int(a.get('colspan',1)),'text':''}
    def handle_data(self,text):
        if self.active is not None:self.active['text']+=text
    def handle_endtag(self,tag):
        if self.active is not None and tag==self.active['tag']:self.cells.append(self.active);self.active=None


def signature(row):
    p=Cells();p.feed(row)
    return [(c['tag'],c['rowspan'],c['colspan'],re.sub(r'\s','',c['text'])) for c in p.cells]


def caption_key(value):return re.sub(r'\s|[（(]\s*续\s*[）)]','',unicodedata.normalize('NFKC',html.unescape(value)))


def merge_tables(doc):
    if doc.get('web_tables')==1:return
    ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text());logical=[];joined=header_rows=0
    source_count=len(doc['tables'])
    for chapter in doc['chapters']:
        path=ROOT/chapter['path'];text=path.read_text();matches=list(BLOCK.finditer(text))
        regions=sorted((r for r in ledger['regions'] if r['kind']=='table' and r['file']==chapter['path'] and r.get('rendered',True)),key=lambda r:(r['page'],r['bbox'][1]))
        if len(matches)!=len(regions):raise ValueError(('Table block/source mismatch',chapter['slug'],len(matches),len(regions)))
        groups=[]
        for match,region in zip(matches,regions):
            info=next(t for t in doc['tables'] if t['page']==region['page'] and t['bbox']==region['bbox'])
            rows=ROWS.findall(match[0]);assert len(rows)==info['rows'],(info['id'],len(rows),info['rows'])
            info['file']=chapter['path']
            previous=groups[-1] if groups else None
            same=bool(previous and not text[previous['end']:match.start()].strip() and caption_key(previous['caption'])==caption_key(info['caption']) and previous['columns']==info['columns'])
            if same:
                group=previous;head=group['header'];n=len(head)
                repeated=n if n and len(rows)>=n and [signature(r) for r in rows[:n]]==[signature(r) for r in head] else 0
                info['web_row_map']=list(range(repeated))+list(range(len(group['rows']),len(group['rows'])+len(rows)-repeated))
                group['rows']+=rows[repeated:];group['end']=match.end();group['parts'].append(info['id']);joined+=1;header_rows+=repeated
            else:
                head=[];header_end=0
                for r,row in enumerate(rows):
                    # Multi-row headers can contain td cells beneath a
                    # spanning th. Keep the complete connected header block.
                    if r<header_end or '<th' in row and '<td' not in row:
                        head.append(row);parser=Cells();parser.feed(row)
                        header_end=max([header_end]+[r+c['rowspan'] for c in parser.cells])
                    else:break
                group={'id':info['id'],'caption':info['caption'],'columns':info['columns'],'start':match.start(),'end':match.end(),'markup':match[0],'rows':rows,'header':head,'parts':[info['id']],'file':chapter['path']}
                groups.append(group);info['web_row_map']=list(range(len(rows)))
            info['logical_table_id']=group['id']
        for group in reversed(groups):
            block=re.sub(r'(<table[^>]*>).*?(</table>)',lambda m:m[1]+'\n'+'\n'.join(group['rows'])+'\n'+m[2],group['markup'],flags=re.S)
            # A continued caption no longer describes the web table.
            block=re.sub(r'(:class: standard-table-caption\s*\n\s*<p>)(.*?)(</p>)',lambda m:m[1]+re.sub(r'[（(]\s*续\s*[）)]','',m[2])+m[3],block,flags=re.S)
            # Untitled examples and message layouts have no source caption.
            # Do not add an invented, repeatedly displayed heading to them.
            if group['caption']=='字段结构':
                block=re.sub(r':::\{div\}\n:class: standard-table-caption\s*\n\s*<p>字段结构</p>\s*\n:::\s*','',block)
            text=text[:group['start']]+block+text[group['end']:]
        path.write_text(text.rstrip()+'\n')
        for group in groups:
            p=Cells();p.feed(''.join(group['rows']))
            logical.append({'id':group['id'],'file':group['file'],'caption':re.sub(r'[（(]\s*续\s*[）)]','',group['caption']),'parts':group['parts'],'rows':len(group['rows']),'columns':group['columns'],'cells':len(p.cells),'merged_cells':sum(c['rowspan']>1 or c['colspan']>1 for c in p.cells),'native_math_cells':sum(bool(re.search(r'\$[^$\n]+\$',c['text'])) for c in p.cells)})
    assert sum(len(t['parts']) for t in logical)==source_count
    doc['logical_tables']=logical;doc['source_tables']=source_count;doc['native_tables']=len(logical);doc['merged_cells']=sum(t['merged_cells'] for t in logical);doc['native_math_cells']=sum(t['native_math_cells'] for t in logical)
    doc['joined_table_parts']=joined;doc['deduplicated_header_rows']=header_rows;doc['web_tables']=1
    from web_edition import recalculate
    recalculate(doc,ledger)
