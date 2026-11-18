"""Verify every physical source cell against the consolidated web table."""
import re
from repair_myst import merge_axes


def audit_tables(source,chapter,actual,doc,local,proof,compare,check_scripts,digest,source_scripts):
    logical=[t for t in doc['logical_tables'] if t['file']==chapter['path']]
    if len(logical)!=len(actual['tables']):raise ValueError((chapter['path'],'logical table count',len(logical),len(actual['tables'])))
    titled=[t for t in logical if t['caption']!='字段结构']
    if len(titled)!=len(actual['captions']):local.append({'file':chapter['path'],'source_captions':len(titled),'html_captions':len(actual['captions']),'type':'caption_count'})
    captions=iter(actual['captions'])
    by_id={t['id']:t for t in source['tables']};count=strict_count=rendered_cells=0
    for logical_info,table in zip(logical,actual['tables']):
        actual_cells={(c['r'],c['c']):c for c in table['cells']};assigned=set();rendered_cells+=len(actual_cells)
        for source_id in logical_info['parts']:
            info=by_id[source_id];boxes=[c['bbox'] for c in info['source_cells']]
            xs=merge_axes([v for c in boxes for v in (c[0],c[2])]);ys=merge_axes([v for c in boxes for v in (c[1],c[3])]);mapping=info['web_row_map']
            for original in info['source_cells']:
                box=original['bbox'];r=min(range(len(ys)),key=lambda i:abs(ys[i]-box[1]));c=min(range(len(xs)),key=lambda i:abs(xs[i]-box[0]));end_r=min(range(len(ys)),key=lambda i:abs(ys[i]-box[3]));end_c=min(range(len(xs)),key=lambda i:abs(xs[i]-box[2]));web_r=mapping[r]
                source_span=(end_r-r,end_c-c);cell=actual_cells.get((web_r,c));assigned.add((web_r,c));count+=1
                if cell is None:
                    local.append({'table':source_id,'source_r':r,'web_r':web_r,'c':c,'type':'missing_source_cell'});continue
                if (cell['rowspan'],cell['colspan'])!=source_span:local.append({'table':source_id,'source_r':r,'web_r':web_r,'c':c,'source_span':source_span,'html_span':[cell['rowspan'],cell['colspan']],'type':'cell_structure'})
                if mapping[r:end_r]!=list(range(web_r,web_r+end_r-r)):local.append({'table':source_id,'r':r,'c':c,'source_rows':mapping[r:end_r],'type':'discontinuous_cell_span'})
                text='\n'.join(original['lines']);strict=not cell['math'] and not cell['scripts'];strict_count+=strict
                diff=compare(text,cell.get('semantic_text',cell['text']),strict=strict)
                if diff:local.append({'file':chapter['path'],'page':info['page'],'table':source_id,'r':r,'web_r':web_r,'c':c,'bbox':box,'source':text,'actual':cell['text'],'math':cell['math'],'scripts':cell['scripts'],'diff':diff,'type':'table_cell'})
                script_issues=check_scripts(original['glyphs'],cell,doc['code'],info['page'])
                if script_issues:local.append({'file':chapter['path'],'page':info['page'],'table':source_id,'r':r,'web_r':web_r,'c':c,'bbox':box,'source':text,'actual':cell['text'],'native_tex':cell['math'],'expected_scripts':script_issues,'actual_scripts':cell.get('script_atoms',[]),'type':'table_scripts'})
                proof.append({'table':logical_info['id'],'source_table':source_id,'r':r,'web_r':web_r,'c':c,'source_sha256':digest(text),'html_sha256':digest(cell.get('semantic_text',cell['text'])),'order_checked':strict,'source_script_groups':len(source_scripts(original['glyphs'])),'matches':not diff and not script_issues})
        if set(actual_cells)!=assigned:local.append({'table':logical_info['id'],'unassigned_web_cells':list(set(actual_cells)-assigned),'type':'cell_structure'})
        if logical_info['caption']!='字段结构':
            caption=next(captions,None)
            diff=compare(logical_info['caption'],caption['text'] if caption else '',strict=True)
            if diff:local.append({'file':chapter['path'],'table':logical_info['id'],'source':logical_info['caption'],'actual':caption['text'] if caption else '', 'diff':diff,'type':'table_caption'})
    return count,strict_count,rendered_cells
