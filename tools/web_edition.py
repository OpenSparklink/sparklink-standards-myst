"""Turn source-faithful PDF transcriptions into a semantic web publication.

Normative text/tables/math remain unchanged. Paper front matter is explicitly
accounted for in the source ledger; URLs and navigation follow real clauses.
"""
from __future__ import annotations
import bisect
from collections import Counter
from dataclasses import dataclass,field
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata
import yaml

ROOT=Path(__file__).resolve().parents[1]
EDITION=2
PAGE_TARGET=45000


def normal(text):
    text=html.unescape(re.sub(r'\\([*_{}\[\]$()<>])',r'\1',text))
    return re.sub(r'\s','',unicodedata.normalize('NFKC',text))


def native_source(text):
    if 'tab-item} 结构化阅读' not in text:return text.split('---',2)[-1].split('\n# ',1)[-1].split('\n',1)[-1]
    body=text.split('tab-item} 结构化阅读',1)[1].split(':::::{tab-item} 原版阅读',1)[0]
    return re.sub(r'\n:{5}\s*$','',body).strip()+'\n'


def title_key(title):
    match=re.match(r'^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)\b',title)
    if match:return match[1].lower().replace('.','-')
    match=re.match(r'^附录\s*([A-Z])',title)
    if match:return 'appendix-'+match[1].lower()
    if title.startswith('前言'):return 'preface'
    if title.startswith('引言'):return 'introduction'
    if title.startswith('参考文献'):return 'references'
    raise ValueError('Unrecognized semantic page title: '+title)


@dataclass
class Section:
    title:str
    depth:int
    pos:tuple
    intro:list[str]=field(default_factory=list)
    children:list['Section']=field(default_factory=list)
    split:bool=False
    path:str=''
    slug:str=''

    def size(self):return len(''.join(self.intro))+sum(c.size() for c in self.children)


def sections(doc,ledger):
    groups=[]
    for chapter in doc['chapters']:
        if chapter['title']=='封面与目录':continue
        if '（续，PDF 第' in chapter['title']:
            assert groups,chapter
            groups[-1].append(chapter)
        else:groups.append([chapter])
    roots=[];discarded=set()
    for group in groups:
        root=Section(group[0]['title'],1,(group[0]['page'],group[0]['y']))
        stack=[root];seen={normal(root.title)}
        for chapter in group:
            body=native_source((ROOT/chapter['path']).read_text())
            heading_blocks=[b for b in ledger['blocks'] if b['file']==chapter['path'] and b['kind'] in ('heading','term_heading','title_fragment')]
            page=chapter['page'];fence=None
            for line in body.splitlines(keepends=True):
                marker=re.match(r'^(`{3,}|~{3,})',line)
                if marker:
                    if fence is None:fence=marker[1]
                    elif marker[1][0]==fence[0] and len(marker[1])>=len(fence):fence=None
                comment=re.match(r'<!-- structured page: (\d+) -->',line)
                if comment:page=int(comment[1])
                heading=None if fence else re.match(r'^(#{2,6}) (.+?)\s*$',line)
                if not heading:
                    stack[-1].intro.append(line);continue
                title=heading[2];key=normal(title)
                matches=[b for b in heading_blocks if normal(b.get('title') or b['source_text'])==key]
                chosen=min(matches,key=lambda b:abs(b['page']-page)) if matches else None
                if key in seen:
                    if chosen:discarded.add((chosen['page'],tuple(chosen['line_ids'])))
                    continue
                seen.add(key)
                pos=(chosen['page'],chosen['bbox'][1]) if chosen else (page,0)
                node=Section(title,len(heading[1]),pos)
                while len(stack)>1 and stack[-1].depth>=node.depth:stack.pop()
                stack[-1].children.append(node);stack.append(node)
        roots.append((root,group))
    return roots,discarded


def selected_pages(node):
    node.split=node.size()>PAGE_TARGET and bool(node.children)
    yield node
    if node.split:
        for child in node.children:yield from selected_pages(child)


def render(node,level=1):
    body=''.join(node.intro)
    if node.split:
        body+='\n:::{div}\n:class: section-links\n\n'
        for child in node.children:body+=f'- [{child.title}]({Path(child.path).name})\n'
        body+='\n:::\n'
    else:
        for child in node.children:body+='\n'+'#'*min(6,level+1)+' '+child.title+'\n\n'+render(child,level+1)
    # Page markers belong to provenance, not the publication source.
    return re.sub(r'<!-- structured page: \d+ -->\s*','',body)


def compact(text):
    from repair_myst import normalize_blank_lines
    return normalize_blank_lines(text)


def figure_alt(text,title):
    def replace(match):
        block=match[0]
        if not re.search(r':alt:.*(?:PDF|原始标注|保留原始)',block):return block
        tail=text[match.end():match.end()+650]
        caption=re.search(r':class: standard-caption\s*\n\s*<p>(.*?)</p>',tail,re.S)
        label=html.unescape(re.sub('<[^>]+>','',caption[1])) if caption else ('协议代码：' if 'source-code' in block else '图示：')+title
        label=re.sub(r'\$([^$]*)\$',lambda m:re.sub(r'[\\{}_^]','',m[1]),label)
        return re.sub(r'^:alt:.*$',lambda _:':alt: '+label,block,flags=re.M)
    return re.sub(r'```\{image\}[^\n]*\n.*?\n```',replace,text,flags=re.S)


def recalculate(doc,ledger):
    active=[b for b in ledger['blocks'] if b.get('rendered',True)]
    doc['paragraph_blocks']=len(active)
    doc['omitted_blocks']=len(ledger['blocks'])-len(active)
    doc['paragraph_kinds']=dict(Counter(b['kind'] for b in active))
    doc['joined_page_paragraphs']=sum(bool(b.get('continuation_of')) for b in active)
    text='\n'.join((ROOT/c['path']).read_text() for c in doc['chapters'])
    doc['native_inline_math']=len(re.findall(r'\$[^$\n]+\$',text))
    doc['native_display_math']=len(re.findall(r'^```\{math\}',text,re.M))
    doc['remaining_math_images']=len(re.findall(r'(?:inline-\d{3}-\d{2}|equation-\d{3})\.png',text))


def upgrade_document(doc,dry_run=False):
    if doc.get('web_edition')==EDITION:return doc
    ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text())
    old_chapters=doc['chapters'];cover=next(c for c in old_chapters if c['title']=='封面与目录')
    cover_text=native_source((ROOT/cover['path']).read_text())
    plain=html.unescape(re.sub('<[^>]*>',' ',cover_text))
    dates=re.search(r'(\d{4}-\d{2}-\d{2})\s*发布\s*(\d{4}-\d{2}-\d{2})\s*实施',plain)
    if dates:doc['published'],doc['effective']=dates.groups()
    part=Path(doc['source']).stem.split('_',1)[1].split('部分-',1)[-1]
    doc['display_title']=part.replace('-',' · ')
    doc['part']=doc['code'].split('.')[-1].split('-')[0]
    roots,discarded=sections(doc,ledger);chapters=[];redirects=[];new_paths=set();ranges=[]
    prefix=re.sub('[^a-z0-9]+','-',doc['code'].lower()).strip('-');directory=Path(doc['index']).parent
    for root,group in roots:
        nodes=list(selected_pages(root))
        for node in nodes:
            key=title_key(node.title)
            node.slug=prefix+('-clause-' if re.match(r'^(?:\d|[a-z]-\d)',key) else '-')+key
            node.path=(directory/(node.slug+'.md')).as_posix()
            if node.path in new_paths:raise ValueError('Duplicate page: '+node.path)
            new_paths.add(node.path)
        end=(group[-1]['end_page'],group[-1]['end_y'])
        for i,node in enumerate(nodes):
            end_pos=nodes[i+1].pos if i+1<len(nodes) else end
            chapter={'title':node.title,'path':node.path,'slug':node.slug,'page':node.pos[0],'y':node.pos[1],'end_page':end_pos[0],'end_y':end_pos[1],'parent':None,'source_chapters':[c['path'] for c in group]}
            parent=next((p for p in reversed(nodes[:i]) if p.split and node in p.children),None)
            if parent:chapter['parent']=parent.path
            chapters.append(chapter)
            if not dry_run:
                front={'title':node.title,'short_title':node.title,'description':doc['standard']+' · '+node.title,'numbering':{'headings':False,'figure':False,'table':False,'equation':False,'subequation':False}}
                body=figure_alt(render(node),node.title)
                # Restoration details belong to the audit, not to every page.
                body=re.sub(r':::\{note\}\n本标准文字与特殊符号已依据原 PDF 字形校验恢复；原版阅读保留逐页对照。\n:::\s*','',body)
                (ROOT/node.path).write_text(compact('---\n'+yaml.safe_dump(front,allow_unicode=True,sort_keys=False).strip()+'\n---\n\n# '+node.title+'\n\n'+body))
        starts=[n.pos for n in nodes]
        if starts!=sorted(starts):raise ValueError(('Non-monotonic source headings',doc['code'],[(n.title,n.pos) for n in nodes]))
        for old in group:
            relevant=[b for b in ledger['blocks'] if b['file']==old['path']]
            first=min(((b['page'],b['bbox'][1]) for b in relevant),default=(old['page'],old['y']))
            destination=nodes[max(0,bisect.bisect_right(starts,first)-1)]
            redirects.append({'from':old['slug'],'to':destination.slug})
        ranges.append((group,nodes,starts))
    for record in ledger['blocks']+ledger['regions']:
        key=(record['page'],tuple(record.get('line_ids',[])))
        if record['file']==cover['path']:
            record['rendered']=False;record['omission_reason']='paper-cover-and-print-contents';continue
        if key in discarded:
            record['rendered']=False;record['omission_reason']='repeated-paper-heading';continue
        for group,nodes,starts in ranges:
            if record['file'] not in [c['path'] for c in group]:continue
            pos=(record['page'],record['bbox'][1]);target=nodes[max(0,bisect.bisect_right(starts,pos)-1)]
            if record.get('kind')=='title_fragment':
                matching=next((n for n in nodes if normal(record['source_text']) in normal(n.title)),None)
                if matching:target=matching
                else:record['rendered']=False;record['omission_reason']='repeated-paper-heading'
            record['source_file']=record['file'];record['file']=target.path;break
    redirects.append({'from':cover['slug'],'to':Path(doc['index']).stem.lower().replace('.','-')})
    # Preserve actual clause nesting in the website sidebar, including pages
    # that were separate entries in the original extraction manifest.
    keys={title_key(c['title']):c for c in chapters}
    for chapter in chapters:
        key=title_key(chapter['title'])
        if key.startswith('appendix-') or key in ('preface','introduction','references'):continue
        parts=key.split('-');parent=None
        for n in range(len(parts)-1,0,-1):
            candidate='-'.join(parts[:n])
            if candidate in keys:parent=keys[candidate];break
            if n==1 and 'appendix-'+candidate in keys:parent=keys['appendix-'+candidate];break
        if parent:chapter['parent']=parent['path']
    doc['chapters']=chapters;doc['legacy_routes']=redirects;doc['web_edition']=EDITION
    doc['source_layout']={'chapters':len(old_chapters),'covers':1,'page_continuations':sum('（续，PDF 第' in c['title'] for c in old_chapters),'removed_classification_labels':len(re.findall(r'ICS\s*|CCS\s*',plain)),'garbled_cover':bool(re.search(r'[\u0590-\u08ff\u0e00-\u1fff\ue000-\uf8ff]',plain))}
    if not dry_run:
        for old in old_chapters:
            if old['path'] not in new_paths:(ROOT/old['path']).unlink(missing_ok=True)
        ledger['kinds']=dict(Counter(b['kind'] for b in ledger['blocks'] if b.get('rendered',True)))
        (ROOT/doc['paragraph_ledger']).write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n')
        recalculate(doc,ledger)
    from web_tables import merge_tables
    if not dry_run:
        from web_continuations import join_paragraphs
        join_paragraphs(doc)
        merge_tables(doc)
    return doc


def upgrade_documents(documents,dry_run=False):
    return [upgrade_document(doc,dry_run) for doc in documents]


FAMILIES={'GBT-48336':('星闪无线通信系统','架构、接入层、基础服务与应用规范'),
          'GBT-46803':('低功耗无线通信网络','基于极化码的物理层与数据链路层规范')}


NAV_TITLES={'101': '架构和通用要求', '102': '媒体接入层标识', '201': 'SLB 空中接口', '202': 'SLB 设备要求与测试', '203': 'SLE 设备要求与测试', '301': '设备发现和传输控制', '302': '服务质量管理', '303': '多域协调与管理', '304': '5G 蜂窝网络融合', '401': '音频流配置与传输', '402': '合作设备集合管理', '403': '媒体控制', '404': '位置信息管理', '405': '视频配置与传输', '406': 'IP 承载管理'}


def card(title,href,description=''):
    return '\n:::{div}\n:class: spec-card\n\n['+title+']('+href+')\n\n'+description+'\n\n:::\n'


def publication_page(path,title,body,short_title=None):
    front={'title':title,'short_title':short_title or title,'numbering':{'headings':False}}
    (ROOT/path).write_text(compact('---\n'+yaml.safe_dump(front,allow_unicode=True,sort_keys=False).strip()+'\n---\n\n# '+title+'\n\n'+body))


def write_publication(documents):
    """Write navigation and product-facing overviews, without paper matter."""
    from web_references import reference_targets
    reference_targets(documents)
    toc=[{'file':'index.md'}]
    for family,(name,description) in FAMILIES.items():
        family_path=f'standards/{family}/{family}.md';children=[]
        body=description+'。\n\n::::{div}\n:class: spec-grid\n'
        for doc in [d for d in documents if d['family']==family]:
            body+=card(doc['part']+' · '+doc['display_title'],Path(doc['index']).relative_to(Path(family_path).parent).as_posix(),doc['standard'])
            by_path={c['path']:{'file':c['path']} for c in doc['chapters']}
            for c in doc['chapters']:
                if c['parent']:by_path[c['parent']].setdefault('children',[]).append(by_path[c['path']])
            children.append({'file':doc['index'],'children':[by_path[c['path']] for c in doc['chapters'] if not c['parent']]})
            ledger=json.loads((ROOT/doc['paragraph_ledger']).read_text())
            scope=next((c for c in doc['chapters'] if re.match(r'^1\s*范围',c['title'])),doc['chapters'][0])
            first=next((b['source_text'] for b in ledger['blocks'] if b['file']==scope['path'] and b['kind']=='paragraph' and b.get('rendered',True)),'')
            summary=re.sub(r'\s+','',first).split('。')[0]+'。' if first else ''
            overview=':::{div}\n:class: spec-version\n\n'+doc['standard']+'\n\n:::\n\n'+summary+'\n\n'
            if doc.get('published'):
                overview+=':::{div}\n:class: spec-dates\n\n发布 '+doc['published']+'　·　实施 '+doc['effective']+'\n\n:::\n\n'
            overview+=':::{div}\n:class: spec-actions\n\n[开始阅读]('+Path(scope['path']).name+')\n\n'
            for label in ['前言','引言']:
                target=next((c for c in doc['chapters'] if c['title'].startswith(label)),None)
                if target:overview+=' ['+label+']('+Path(target['path']).name+')'
            overview+='\n\n:::\n\n'
            topics=[c for c in doc['chapters'] if not c['parent'] and re.match(r'^(?:[5-9]|1\d)\s',c['title'])][:6]
            if topics:
                overview+='## 技术主题\n\n::::{div}\n:class: spec-grid\n'
                for c in topics:overview+=card(c['title'],Path(c['path']).name)
                overview+='\n::::\n'
            publication_page(doc['index'],doc['display_title'],overview,doc['part']+' · '+NAV_TITLES.get(doc['part'],doc['display_title']))
        body+='\n::::\n'
        publication_page(family_path,name,body)
        toc.append({'file':family_path,'children':children})
    home=':::{div}\n:class: spec-lead\n\n架构、协议与应用，按条款查阅。\n\n:::\n\n覆盖星闪无线通信系统及基于极化码的低功耗无线通信网络，共 17 份标准。可直接搜索术语、协议字段和技术条款。\n\n::::{div}\n:class: spec-grid\n'
    for family,(name,description) in FAMILIES.items():home+=card(name,f'standards/{family}/{family}.md',description)
    home+='\n::::\n\n## 常用规范\n\n::::{div}\n:class: spec-grid\n'
    for part in ['101','201','202','301']:
        d=next(d for d in documents if d['family']=='GBT-48336' and d['part']==part)
        home+=card(d['display_title'],d['index'])
    home+='\n::::\n'
    publication_page('index.md','SparkLink 技术规范',home,'规范首页')
    config={'version':1,'project':{'title':'SparkLink 技术规范','description':'星闪无线通信系统与低功耗无线通信网络技术规范','plugins':['tools/math_in_html.mjs'],'numbering':{'equation':False,'subequation':False},'toc':toc},'site':{'template':'book-theme','options':{'style':'./styles/reader.css','logo_text':'SparkLink Docs','favicon':'./assets/brand/favicon.ico','hide_footer_links':False,'hide_authors':True,'hide_outline':True,'outline_maxdepth':3}}}
    (ROOT/'myst.yml').write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False,width=300))
    totals={'documents':len(documents),'pages':sum(d['pages'] for d in documents),'chapters':sum(len(d['chapters']) for d in documents),'paragraph_kinds':dict(sum((Counter(d['paragraph_kinds']) for d in documents),Counter()))}
    for key in ['native_tables','merged_cells','table_fallbacks','paragraph_blocks','joined_page_paragraphs','native_inline_math','native_display_math','native_math_cells','remaining_math_images','omitted_blocks','source_tables','joined_table_parts','deduplicated_header_rows']:totals[key]=sum(d.get(key,0) for d in documents)
    totals['joined_chunk_paragraphs']=sum(len(d.get('joined_chunk_paragraphs',[])) for d in documents)
    data={'web_edition':EDITION,'documents':documents,'totals':totals}
    (ROOT/'metadata/reading-manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    inventory={'source_documents':len(documents),'source_layout_chapters':sum(d['source_layout']['chapters'] for d in documents),'removed_covers':sum(d['source_layout']['covers'] for d in documents),'garbled_covers':sum(d['source_layout']['garbled_cover'] for d in documents),'removed_pdf_continuations':sum(d['source_layout']['page_continuations'] for d in documents),'semantic_pages':totals['chapters'],'omitted_blocks':totals['omitted_blocks'],'policy':'Only paper covers, printed tables of contents, repeated headings and PDF presentation are omitted. Every omitted source block remains explicit in the provenance ledger. Normative body, figures, tables and mathematics remain source-verifiable.','documents':[{'code':d['code'],**d['source_layout']} for d in documents]}
    inventory.update(source_table_parts=totals['source_tables'],web_tables=totals['native_tables'],joined_table_parts=totals['joined_table_parts'],deduplicated_header_rows=totals['deduplicated_header_rows'],joined_paragraphs_at_old_chunk_boundaries=totals['joined_chunk_paragraphs'],legacy_redirects=sum(len(d['legacy_routes']) for d in documents),retained_figures=sum(sum(r.get('rendered',True) and bool(r.get('asset')) for r in json.loads((ROOT/d['paragraph_ledger']).read_text())['regions']) for d in documents))
    (ROOT/'metadata/web-edition-inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n')
    return data


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    manifest=json.loads((ROOT/'metadata/reading-manifest.json').read_text())
    upgraded=upgrade_documents(manifest['documents'],dry_run=not args.apply)
    for d in upgraded:print(d['code'],len(d['chapters']),'semantic pages')
    print('Total',sum(len(d['chapters']) for d in upgraded))
    if args.apply:
        from repair_myst import write_project
        write_project(upgraded)
