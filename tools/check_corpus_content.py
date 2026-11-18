#!/usr/bin/env python3
"""Compare all captured HTML blocks and individual cells with PDF source."""
import hashlib
import json
import os
import re
import unicodedata
import statistics
from collections import Counter,defaultdict
from pathlib import Path
from repair_myst import merge_axes
from reviewed_math import entries as reviewed_entries,qam_latex

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/full-audit'
REVIEW_PATH=ROOT/'metadata/corpus-script-reviews.json'
REVIEWS=json.loads(REVIEW_PATH.read_text())['reviews'] if REVIEW_PATH.exists() else []
REVIEWED=[]


def review_digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def resolve_geometry(warnings,block,node,code,pdf_sha256,text):
    """Accept only a visually reviewed, exact source/TeX/model disagreement."""
    if not warnings:return warnings
    for review in REVIEWS:
        if (review['code'],review['page'],review['line_ids'])!=(code,block['page'],block['line_ids']):continue
        if (review['status']=='verified' and review['source_pdf_sha256']==pdf_sha256
            and review['source_text_sha256']==review_digest(text)
            and review['native_tex_sha256']==review_digest(node['math'])
            and review['geometry_warning_sha256']==review_digest(warnings)
            and (ROOT/review['evidence']).is_file()):
            REVIEWED.append({'code':code,'page':block['page'],'line_ids':block['line_ids'],'evidence':review['evidence'],'reason':review['reason']})
            return []
    return warnings


def canonical(s):
    s=re.sub(r'>\s*=','≥',s);s=re.sub(r'<\s*=','≤',s)
    return unicodedata.normalize('NFKC',s).translate(str.maketrans({'ϕ':'φ','ϵ':'ε','ϑ':'θ','ς':'σ','µ':'μ','ˆ':'^','−':'-','‐':'-','‑':'-','⁃':'-','⋅':'·','⋯':'…','\U00100ba8':'˜','\U00100c4b':'⊗'}))


def letters(s):return ''.join(c for c in canonical(s) if c.isalnum() or c=='_')
def chinese(s):return ''.join(re.findall(r'[\u3400-\u9fff]',s))
def compact(s):return re.sub(r'\s+|[\u200b\u2061-\u2064]','',canonical(s))


def source_scripts(glyphs):
    """Find reduced glyphs beside a larger source baseline, independently
    of the converter's span grouping and HTML/LaTeX choices."""
    glyphs=[dict(g,x=g.get('ink_x',g['x'])) for g in glyphs]
    # The damaged Greek font's PDF origins are offset from the surrounding
    # mathematical baseline. Derive that baseline from adjacent Latin math
    # at the main size; the glyph's own y is not a typographic baseline.
    for g in glyphs:
        if g['font']!='FzBookMaker15DlFont15':continue
        anchors=[a for a in glyphs if a['font'] in ('FzBookMaker13DlFont13','FzBookMaker2DlFont2') and letters(a['c']) and abs(a['x']-g['x'])<40 and abs(a['y']-g['y'])<g['size']*.8 and a['size']>=g['size']*.8]
        if anchors:
            largest=max(a['size'] for a in anchors)
            g['y']=statistics.median(a['y'] for a in anchors if a['size']>=largest*.94)
    candidates=[]
    letter_glyphs=[g for g in glyphs if letters(g['c'])]
    buckets=defaultdict(list)
    for g in letter_glyphs:buckets[int(g['x']//16),int(g['y']//8)].append(g)
    maximum=max((g['size'] for g in letter_glyphs),default=10)
    for g in glyphs:
        if not letters(g['c']) and g['c'] not in '-−+()':continue
        if g['size']>=maximum*.94:continue
        x,y=int(g['x']//16),int(g['y']//8)
        near=[b for dx in range(-int(maximum*3/16)-1,2) for dy in range(-int(maximum/8)-1,int(maximum/8)+2) for b in buckets[x+dx,y+dy]]
        bases=[b for b in near if b['size']>g['size']/0.94 and b['x']<=g['x']+.2 and g['x']-b['x']<b['size']*3 and 1<abs(b['y']-g['y'])<b['size']*.85]
        mathematical=[b for b in bases if not chinese(b['c'])]
        bases=mathematical or [b for b in bases if g['x']-b['x']<b['size']*1.2]
        if not bases:continue
        base=min(bases,key=lambda b:abs(g['y']-b['y'])+(g['x']-b['x'])*.15)
        candidates.append({**g,'kind':'sup' if g['y']<base['y'] else 'sub','base':base['c'],'base_y':base['y'],'base_x':base['x']})
    groups=[]
    for g in sorted(candidates,key=lambda g:(g['y'],g['x'])):
        if groups and g['kind']==groups[-1]['kind'] and abs(g['base_x']-groups[-1]['base_x'])<.5 and abs(g['base_y']-groups[-1]['base_y'])<.5 and abs(g['y']-groups[-1]['y'])<.6 and g['x']-groups[-1]['last_x']<g['size']*2:
            groups[-1]['text']+=g['c'];groups[-1]['last_x']=g['x']
        else:groups.append({'kind':g['kind'],'base':g['base'],'base_x':g['base_x'],'base_y':g['base_y'],'text':g['c'],'y':g['y'],'last_x':g['x']})
    return groups


def check_scripts(glyphs,node,code=None,page=None):
    missing=[]
    for source in source_scripts(glyphs):
        signature=lambda s:''.join(c for c in canonical(s) if c.isalnum() or c in '+-×÷')
        text=signature(source['text'])
        if not text:continue
        expected=Counter(text)
        matches=[s for s in node.get('script_atoms',[]) if s['kind']==source['kind'] and not expected-Counter(signature(s['text'])) and (not signature(s.get('base','')) or any(signature(source['base']) in signature(parent) for parent in [s['base']]+s.get('ancestors',[])))]
        if not matches:
            explicit=False
            for entry in reviewed_entries() if code else []:
                if entry['code']!=code or entry['page']!=page:continue
                x0,y0,x1,y1=entry['bbox']
                if not x0-2<=source['last_x']<=x1+2 or not y0-2<=source['y']<=y1+2:continue
                values=[entry['latex']] if entry.get('latex') else [qam_latex(*entry['qam'])] if entry.get('qam') else re.findall(r'\$([^$\n]+)\$',entry.get('markup',''))
                values=[re.sub(r'\\tag\{[^}]+\}','',s).strip() for s in values]
                if any(value in node['math'] for value in values):explicit=True;break
            if not explicit:missing.append(source)
    return missing


def compare(source,actual,strict=False):
    a,b=Counter(letters(source)),Counter(letters(actual));missing,extra=a-b,b-a
    han=chinese(source)==chinese(actual)
    result={}
    if missing:result['missing']=dict(missing)
    if extra:result['extra']=dict(extra)
    if not han:result['chinese_order']=False
    if strict and letters(source)!=letters(actual):result['character_order']=False
    operators=lambda s:Counter(c for c in canonical(s) if c in '+-×÷≤≥≠±∈∉∪∩∖⊕⊗')
    oa,ob=operators(source),operators(actual)
    if oa-ob:result['missing_operators']=dict(oa-ob)
    if ob-oa:result['extra_operators']=dict(ob-oa)
    return result


def main():
    mp=ROOT/'metadata/reading-manifest.json';manifest=json.loads(mp.read_text());issues=[];results=[]
    cell_proof=[];block_proof=[];chapter_proof=[];rendered_cells=0
    digest=lambda s:hashlib.sha256(canonical(s).encode()).hexdigest()
    for doc in manifest['documents']:
        if os.environ.get('CHECK_DOCUMENT') and doc['code']!=os.environ['CHECK_DOCUMENT']:continue
        source=json.loads((OUT/'source'/(doc['code']+'.json')).read_text())
        if source['source_sha256']!=doc['sha256']:raise ValueError('Outdated PDF audit: '+doc['code'])
        dom=json.loads((OUT/'dom'/(doc['code']+'.json')).read_text());by_file={c['path']:c for c in dom}
        records=[dict(b,comparison_text=b.get('reading_order_text') or b.get('semantic_source') or b['source_text']) for b in source['blocks'] if b.get('rendered',True)]
        by_line={(b['page'],i):b for b in records for i in b['line_ids']}
        by_key={(b['page'],tuple(b['line_ids'])):b for b in records}
        for b in records:
            if b['kind']=='math_fragment':by_line[b['page'],b['math_fragment_of']]['comparison_text']+='\n'+b['source_text']
        for b in records:
            if b.get('continuation_of'):
                target=b['continuation_of'];by_key[target['page'],tuple(target['line_ids'])]['comparison_text']+='\n'+b['comparison_text']
        local=[dict(type='source_ledger',**i) for i in source['source_issues']];block_count=cell_count=strict_cells=0;source_nodes={}
        for chapter in doc['chapters']:
            actual=by_file[chapter['path']];selected=[b for b in records if b['file']==chapter['path'] and not b.get('continuation_of')]
            if actual.get('markdown_sha256')!=hashlib.sha256((ROOT/chapter['path']).read_bytes()).hexdigest():raise ValueError('Outdated DOM capture: '+chapter['path'])
            html_path='_build/html/'+chapter['slug']+'/index.html'
            if actual.get('html_sha256')!=hashlib.sha256((ROOT/html_path).read_bytes()).hexdigest():raise ValueError('Outdated HTML capture: '+chapter['path'])
            chapter_proof.append({'file':chapter['path'],'markdown_sha256':actual['markdown_sha256'],'html_file':html_path,'html_sha256':actual['html_sha256']})
            for kind,nodes in actual['blocks'].items():
                expected=sorted((b for b in selected if b['kind']==kind),key=lambda b:(b['page'],b['bbox'][1]))
                if any(b.get('render_counts') for b in selected):
                    # The source-reviewed multi-item region is compared as a
                    # single complete region below, rather than guessed apart.
                    if kind in ('paragraph','list_item'):continue
                if len(expected)!=len(nodes):
                    local.append({'file':chapter['path'],'kind':kind,'expected':len(expected),'actual':len(nodes),'type':'block_count'});continue
                for b,node in zip(expected,nodes):
                    source_nodes[b['page'],tuple(b['line_ids'])]=node
                    text=b['comparison_text']
                    if kind=='equation':text=re.sub(r'(?:[.·…]\s*){2,}[（(]\s*\d+\s*[）)]','',text)
                    diff=compare(text,node.get('semantic_text',node['text']));block_count+=1
                    if diff:local.append({'file':chapter['path'],'page':b['page'],'line_ids':b['line_ids'],'kind':kind,'source':text,'actual':node['text'],'math':node['math'],'diff':diff,'type':'block_text'})
                    script_issues=check_scripts(b.get('source_glyphs',[]),node,doc['code'],b['page'])
                    script_issues=resolve_geometry(script_issues,b,node,doc['code'],doc['sha256'],text)
                    if script_issues:local.append({'file':chapter['path'],'page':b['page'],'line_ids':b['line_ids'],'bbox':b['bbox'],'kind':kind,'source':text,'actual':node['text'],'native_tex':node['math'],'expected_scripts':script_issues,'actual_scripts':node.get('script_atoms',[]),'type':'block_scripts'})
                    block_proof.append({'code':doc['code'],'file':chapter['path'],'page':b['page'],'kind':kind,'line_ids':b['line_ids'],'source_sha256':digest(text),'html_sha256':digest(node.get('semantic_text',node['text'])),'math_sha256':review_digest(node['math']),'script_tree_sha256':review_digest(node.get('script_atoms',[])),'matches':not diff and not script_issues})
            if any(b.get('render_counts') for b in selected):
                cursor=0
                for b in sorted((b for b in selected if b['kind'] in ('paragraph','list_item')),key=lambda b:(b['page'],b['bbox'][1])):
                    count=sum(b.get('render_counts',{}).values()) or 1
                    nodes=actual['paragraph_list_flow'][cursor:cursor+count];cursor+=count
                    text=''.join(n.get('semantic_text',n['text']) for n in nodes)
                    source_nodes[b['page'],tuple(b['line_ids'])]=nodes[0] if count==1 else {'text':text,'semantic_text':text,'math':[t for n in nodes for t in n['math']],'script_atoms':[s for n in nodes for s in n.get('script_atoms',[])]}
                    diff=compare(b['comparison_text'],text);block_count+=1
                    if diff:local.append({'file':chapter['path'],'page':b['page'],'kind':b['kind'],'source':b['comparison_text'],'actual':text,'diff':diff,'type':'reviewed_multi_block'})
                    block_proof.append({'code':doc['code'],'file':chapter['path'],'page':b['page'],'kind':b['kind'],'line_ids':b['line_ids'],'source_sha256':digest(b['comparison_text']),'html_sha256':digest(text),'matches':not diff})
                if cursor!=len(actual['paragraph_list_flow']):raise ValueError('Unassigned paragraph/list flow')
            for b in (r for r in records if r['file']==chapter['path'] and r.get('continuation_of')):
                target=b['continuation_of']
                while by_key[target['page'],tuple(target['line_ids'])].get('continuation_of'):target=by_key[target['page'],tuple(target['line_ids'])]['continuation_of']
                node=source_nodes[target['page'],tuple(target['line_ids'])]
                script_issues=check_scripts(b.get('source_glyphs',[]),node,doc['code'],b['page'])
                script_issues=resolve_geometry(script_issues,b,node,doc['code'],doc['sha256'],b['comparison_text'])
                if script_issues:local.append({'file':chapter['path'],'page':b['page'],'line_ids':b['line_ids'],'bbox':b['bbox'],'kind':'continuation','source':b['comparison_text'],'actual':node['text'],'native_tex':node['math'],'expected_scripts':script_issues,'actual_scripts':node.get('script_atoms',[]),'type':'block_scripts'})
            from table_audit import audit_tables
            cell_n,strict_n,rendered_n=audit_tables(source,chapter,actual,doc,local,cell_proof,compare,check_scripts,digest,source_scripts)
            cell_count+=cell_n;strict_cells+=strict_n;rendered_cells+=rendered_n
            for b in selected:
                if b['kind'] in ('heading','term_heading'):
                    text=b.get('title') or b['comparison_text']
                    if not any(letters(text)==letters(h['text']) for h in actual['headings']):
                        local.append({'file':chapter['path'],'page':b['page'],'source':text,'type':'source_heading'})
                elif b['kind']=='title_fragment' and letters(b['source_text']) not in letters(chapter['title']):
                    local.append({'file':chapter['path'],'page':b['page'],'source':b['source_text'],'title':chapter['title'],'type':'source_title_fragment'})
        row={'code':doc['code'],'source_pdf_sha256':doc['sha256'],'ledger_sha256':hashlib.sha256((ROOT/doc['paragraph_ledger']).read_bytes()).hexdigest(),'blocks':block_count,'cells':cell_count,'cells_in_source_order':strict_cells,'source_issues':len(source['source_issues']),'issues':len(local)};results.append(row)
        issues.extend(dict(code=doc['code'],**i) for i in local)
        print(json.dumps(row),flush=True)
    report={'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'documents':len(results),'blocks':sum(r['blocks'] for r in results),'cells':sum(r['cells'] for r in results),'ordered_cells':sum(r['cells_in_source_order'] for r in results),'tables':sum(d['native_tables'] for d in manifest['documents']),'physical_source_tables':sum(d.get('source_tables',d['native_tables']) for d in manifest['documents']),'source_blocks':manifest['totals']['paragraph_blocks'],'source_kinds':manifest['totals']['paragraph_kinds'],'joined_page_segments':manifest['totals']['joined_page_paragraphs'],'comparison':{'chinese':'Ordered characters per source block/cell','letters_numbers':'Case-sensitive character counts; ordered content for cells without mathematical reflow','operators':'Critical operator counts with equivalent Unicode and comparison spellings normalized','scripts':'PDF glyph geometry against MathML script trees; explicit source-reviewed LaTeX regions matched exactly','table_structure':'Every cell position, rowspan and colspan against source cell rectangles'},'issues':issues,'results':results}
    report['reviewed_geometry_disagreements']=REVIEWED
    report['chapter_snapshots']=chapter_proof
    report['rendered_cells']=rendered_cells
    report['reader_sha256']=hashlib.sha256((ROOT/'_build/html/reader.js').read_bytes()).hexdigest()
    report['comparison']['scripts']+='; exact hash-bound visual adjudication of ambiguous PDF baselines'
    (OUT/'content-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    for name,rows in [('cell-checks',cell_proof),('block-checks',block_proof)]:
        (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows))
    print('Issues',len(issues))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
