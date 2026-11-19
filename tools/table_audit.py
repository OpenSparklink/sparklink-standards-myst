"""Verify every physical source cell against the consolidated web table."""
import re
from repair_myst import merge_axes
from prepare_corpus_audit import cell_lines


WRAPPED_FIELDS = (
    ('newSecurityContext-', 'D信元', 'I'),
    ('xrcRecon-', 'igurationComplete', 'f'),
    ('xrcReconfigura-', 'ionComplete', 't'),
    ('sens-', 'ngCapabilityResponse', 'i'),
    ('sensingCapabili-', 'yResponse', 't'),
    ('newSecurityCon-', 'extID', 't'),
)


def separate_row_glyphs(cells):
    """Recover assignments, list markers and field names that straddle a rule."""
    by_edge = {(cell['bbox'][1], cell['bbox'][2]): cell for cell in cells}
    for right in cells:
        x, y, _, bottom = right['bbox']
        left = by_edge.get((y, x))
        if not left or left['bbox'][3] != bottom:
            continue
        label = ''.join(left['lines'])
        glyph_pairs = {
            (missing, suffix[0])
            for prefix, suffix, missing in WRAPPED_FIELDS
            if any(a.endswith(prefix) and b.startswith(suffix)
                   for a,b in zip(right['lines'],right['lines'][1:]))
        }
        assignment = re.fullmatch(r'(?:初始化|步骤\d+)([ijkm])|([ijkm])步骤\d+', label)
        if assignment and right['lines'] and right['lines'][0].startswith('='):
            glyph_pairs.add((assignment[1] or assignment[2], '='))
        elif any(line.startswith(')') for line in right['lines']):
            glyph_pairs.update((line, ')') for line in left['lines'] if re.fullmatch('[a-z]', line))
        if not glyph_pairs:
            continue
        edges = [g for g in right['glyphs'] if x <= g['x'] <= x + 8]
        move = [
            g for g in left['glyphs']
            if x - 2 <= g['x'] < x
            and any((g['c'], edge['c']) in glyph_pairs and abs(g['y'] - edge['y']) < 2 for edge in edges)
        ]
        if move:
            left['glyphs'] = [g for g in left['glyphs'] if g not in move]
            right['glyphs'].extend(move)
            for cell in (left, right):
                cell['lines'] = cell_lines(cell['glyphs'])


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
            if doc['code']=='GBT-48336.202-2026':
                separate_row_glyphs(info['source_cells'])
            xs=merge_axes([v for c in boxes for v in (c[0],c[2])]);ys=merge_axes([v for c in boxes for v in (c[1],c[3])]);mapping=info['web_row_map']
            for original in info['source_cells']:
                box=original['bbox'];r=min(range(len(ys)),key=lambda i:abs(ys[i]-box[1]));c=min(range(len(xs)),key=lambda i:abs(xs[i]-box[0]));end_r=min(range(len(ys)),key=lambda i:abs(ys[i]-box[3]));end_c=min(range(len(xs)),key=lambda i:abs(xs[i]-box[2]));web_r=mapping[r]
                source_span=(end_r-r,end_c-c);cell=actual_cells.get((web_r,c));assigned.add((web_r,c));count+=1
                if cell is None:
                    local.append({'table':source_id,'source_r':r,'web_r':web_r,'c':c,'type':'missing_source_cell'});continue
                if (cell['rowspan'],cell['colspan'])!=source_span:local.append({'table':source_id,'source_r':r,'web_r':web_r,'c':c,'source_span':source_span,'html_span':[cell['rowspan'],cell['colspan']],'type':'cell_structure'})
                if mapping[r:end_r]!=list(range(web_r,web_r+end_r-r)):local.append({'table':source_id,'r':r,'c':c,'source_rows':mapping[r:end_r],'type':'discontinuous_cell_span'})
                text='\n'.join(original['lines']);strict=not cell['math'] and not cell['scripts'];strict_count+=strict
                # The source PDF paints the period before "in", while the
                # glyph origins put it between the overlapping "i" and "n".
                reading_text=text.replace('ConnectionStatusi.n-\ndication','ConnectionStatus.in-\ndication')
                # The printed space separates two fields on the same baseline.
                reading_text=reading_text.replace(
                    'dedicatedACK-ResourceSetConftim-\ningAdvanceInfo',
                    'dedicatedACK-ResourceSetConf timingAdvanceInfo',
                )
                diff=compare(reading_text,cell.get('semantic_text',cell['text']),strict=strict)
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
