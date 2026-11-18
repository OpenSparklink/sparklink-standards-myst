"""Paragraph-level structure and provenance, independent of PDF line wrapping."""
from __future__ import annotations
import html
import re
import statistics
from functools import lru_cache
from pathlib import Path
import yaml


@lru_cache(maxsize=1)
def term_spacing():
    data=yaml.safe_load((Path(__file__).resolve().parents[1]/'metadata/term-spacing.yml').read_text())
    patterns=[]
    for key,value in sorted(data.items(),key=lambda pair:-len(pair[0])):
        assert re.sub(r'\s','',value)==key
        patterns.append((re.compile(r'\b'+r'\s*'.join(re.escape(c) for c in key)+r'\b'),value))
    return patterns


def format_term(title):
    for pattern,value in term_spacing():title=pattern.sub(value,title)
    return re.sub(r'(?<=[A-Za-z]);(?=[A-Za-z])','; ',title)


def text_join(parts):
    result=''
    for part in parts:
        part=part.strip()
        if result and part and re.search(r'[A-Za-z0-9]$',re.sub('<[^>]+>','',result)) and re.match(r'[A-Za-z0-9]',re.sub('<[^>]+>','',part)):
            result+=' '
        result+=part
    return result


def bold_span(span):
    return bool(span.get('flags',0)&16 or re.search(r'HT|Hei|Bold|Heiti|^FzBookMaker(?:0DlFont0|5DlFont)',span.get('font',''),re.I))


def rich_line(line):
    spans=line.get('spans',[])
    if not spans or line.get('ocr') and not any('_html' in s for s in spans):
        return html.escape(line['text'])
    sizes=[s['size'] for s in spans if s['text'].strip() and '_html' not in s]
    if not sizes:sizes=[s['size'] for s in spans if s['text'].strip()]
    if not sizes:return ''
    base=max(sizes)
    baselines=[s['origin'][1] for s in spans if s['size']>=base*.9]
    baseline=statistics.median(baselines) if baselines else line['y']
    result=''
    previous=None
    for span in sorted(spans,key=lambda s:s['bbox'][0]):
        if '_html' in span:
            result+=span['_html'];previous=span;continue
        text=html.escape(span['text'])
        if not text:continue
        if previous and span.get('_advance_bbox',span['bbox'])[0]-previous.get('_advance_bbox',previous['bbox'])[2]>1.8 and not result.endswith(' ') and not text.startswith(' '):result+=' '
        if span.get('flags',0)&1 and span['size']<base*.9 or span['size']<base*.88 and span['origin'][1]<baseline-1:
            text='<sup>'+text+'</sup>'
        elif span['size']<base*.88 and span['origin'][1]>baseline+1:
            text='<sub>'+text+'</sub>'
        elif bold_span(span):
            text='<strong>'+text+'</strong>'
        result+=text
        previous=span
    return result.strip()


def list_marker(text):
    match=re.match(r'^(——+|—|[•●▪]|·(?=\s*[\u3400-\u9fff])|[a-zA-Z][)）]|\d+[)）])\s*(.*)$',text)
    if not match:return None
    marker,body=match.groups()
    kind='dash' if marker.startswith('—') or marker in '•●▪·' else 'alpha' if marker[0].isalpha() else 'decimal'
    return {'marker':marker,'body':body,'kind':kind,'start':ord(marker[0].lower())-96 if kind=='alpha' else int(marker[:-1]) if kind=='decimal' else 1}


def prepare_list_markers(lines):
    """Keep a bullet out of a mathematical assignment on the same span."""
    for line in lines:
        if line.get('_list_marker_split'):continue
        match=re.match(r'^\s*(——+|—|[•●▪])',line['text'])
        if not match:continue
        remaining=len(match[0]);rebuilt=[]
        for original in line['spans']:
            if not remaining:rebuilt.append(original);continue
            count=min(remaining,len(original['text']));remaining-=count
            prefix=dict(original);prefix['text']=original['text'][:count]
            prefix['source_text']=original.get('source_text',original['text'])[:count]
            prefix['_math_handled']=True;rebuilt.append(prefix)
            if count<len(original['text']):
                suffix=dict(original);suffix['text']=original['text'][count:]
                suffix['source_text']=original.get('source_text',original['text'])[count:]
                if original.get('_glyphs'):
                    suffix['_glyphs']=original['_glyphs'][count:]
                    prefix['_glyphs']=original['_glyphs'][:count]
                    suffix['origin']=suffix['_glyphs'][0]['origin']
                    suffix['bbox']=(min(g['bbox'][0] for g in suffix['_glyphs']),min(g['bbox'][1] for g in suffix['_glyphs']),max(g['bbox'][2] for g in suffix['_glyphs']),max(g['bbox'][3] for g in suffix['_glyphs']))
                rebuilt.append(suffix)
        line['spans']=rebuilt;line['_list_marker_split']=True


def list_html(items):
    # PDF indentation and marker families determine nesting. Keep the original
    # marker and line IDs in the ledger, and emit real list/listItem nodes.
    output=[]
    stack=[]
    base=min(item['x'] for item in items)
    previous_kind=None
    for item in items:
        level=max(0,min(3,round((item['x']-base)/24)))
        if previous_kind=='alpha' and item['kind']=='decimal' and stack and level==0:level=1
        if previous_kind=='decimal' and item['kind']=='alpha' and level==0:level=0
        tag='ul' if item['kind']=='dash' else 'ol'
        cls='standard-list' if tag=='ul' else item['kind']+'-list'
        while len(stack)>level+1:
            output.append('</li></'+stack.pop()+'>')
        if len(stack)==level+1 and stack[-1]!=tag:
            output.append('</li></'+stack.pop()+'>')
        if len(stack)<=level:
            attrs='' if tag=='ul' else f' start="{item["start"]}"'
            output.append(f'<{tag} class="{cls}"{attrs}>')
            stack.append(tag)
        else:output.append('</li>')
        first={**item['lines'][0],'text':item['body']}
        if first.get('spans') and not first.get('ocr'):
            spans=[dict(s) for s in first['spans']]
            prefix=re.match(r'^\s*'+re.escape(item['marker'])+r'\s*',''.join(s['text'] for s in spans))
            remove=prefix.end() if prefix else 0
            for span in spans:
                count=min(remove,len(span['text']));span['text']=span['text'][count:];remove-=count
            first['spans']=spans
        body=text_join([rich_line(first)]+[rich_line(l) for l in item['lines'][1:]])
        output.append('<li><p>'+html.escape(item['marker'])+' '+body+'</p>')
        previous_kind=item['kind']
    while stack:output.append('</li></'+stack.pop()+'>')
    return '\n'.join(output)


def organize(lines, *, page_number, min_y, max_y, page_height, page_width, excluded, regions,
             is_heading, escape_md, equation, breaks, ledger,root_title=''):
    """Classify each available source line exactly once and assemble paragraphs."""
    available=[]
    for i,line in enumerate(lines):
        box=line['bbox'];text=line['text']
        if i in excluded or not min_y<=box[1]<max_y:continue
        if re.match(r'^GB\s*/?\s*T\s*\d',text) and (box[1]<95 or box[1]>page_height-65):continue
        if re.fullmatch(r'[\dⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+',text) and box[1]>page_height-90:continue
        cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
        if any(r[0]<=cx<=r[2] and r[1]<=cy<=r[3] for r in regions):continue
        if not text.strip():continue
        available.append((i,line))
    sizes=[s['size'] for _,l in available for s in l.get('spans',[]) if s['text'].strip()]
    font=statistics.median(sizes) if sizes else 10
    lefts=[l['bbox'][0] for _,l in available if len(l['text'])>5 and not is_heading(l)]
    left=min(lefts) if lefts else min((l['bbox'][0] for _,l in available),default=50)
    events=[]
    blocks=[]
    current=None
    items=[]
    consumed=set()

    def add_record(kind,source_lines,**extra):
        record={'page':page_number,'kind':kind,'line_ids':[i for i,_ in source_lines],
                'source_text':'\n'.join(l['text'] for _,l in source_lines),
                'bbox':[min(l['bbox'][0] for _,l in source_lines),min(l['bbox'][1] for _,l in source_lines),
                        max(l['bbox'][2] for _,l in source_lines),max(l['bbox'][3] for _,l in source_lines)],**extra}
        ledger.append(record);return record

    def flush_items():
        nonlocal items
        if not items:return
        events.append((items[0]['lines'][0]['bbox'][1],2,list_html(items)))
        for item in items:add_record('list_item',item['source_lines'],marker=item['marker'],list_kind=item['kind'])
        items=[]

    def flush():
        nonlocal current
        if not current:return
        source=current['source'];kind=current['kind'];ls=[l for _,l in source]
        body=text_join([rich_line(l) for l in ls])
        if kind=='paragraph' and '<img ' in body and not html.unescape(re.sub('<[^>]+>','',body)).strip():
            kind='equation'
            markup=f':::{{div}}\n:class: source-equation-block\n\n{body}\n\n:::'
        elif kind in ('note','example'):
            label=current['label']
            first=html.escape(re.sub(r'^(?:注\s*\d*|示例\s*\d*)\s*[：:]?\s*','',ls[0]['text']))
            body=text_join([first]+[rich_line(l) for l in ls[1:]])
            markup=f':::{{admonition}} {label}\n:class: {"note" if kind=="note" else "tip"}\n\n<p>{body}</p>\n\n:::'
        elif kind=='definition':
            parts=re.split(r'—+|[：:]',rich_line(ls[0]),maxsplit=1)
            if len(parts)<2:parts=[html.escape(p) for p in re.split(r'—+|[：:]',ls[0]['text'],maxsplit=1)]
            term,definition=parts
            if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 /⁃-]*', term.strip()):
                term = term.replace('⁃', '-')
            body=text_join([definition]+[rich_line(l) for l in ls[1:]])
            markup=f'<dl class="standard-definitions"><dt>{term.strip()}</dt><dd>{body}</dd></dl>'
        else:
            markup=f'<p class="standard-{kind}">{body}</p>'
        events.append((ls[0]['bbox'][1],2,markup))
        add_record(kind,source)
        current=None

    previous=None
    for pos,(i,line) in enumerate(available):
        if i in consumed:continue
        text=line['text'];box=line['bbox']
        if line.get('_math_empty'):
            add_record('math_fragment',[(i,line)],math_fragment_of=line['_math_fragment_of']);continue
        # Source tables/figures break a paragraph even when the surrounding
        # PDF baselines happen to be close to one another.
        barrier=previous and any(previous['bbox'][3]<=y<=box[1] for y in breaks)
        if barrier:flush();flush_items()
        normalized=re.sub(r'\s+','',text)
        title_key=lambda s:re.sub(r'\s+','',s).translate(str.maketrans('（）','()'))
        if root_title.startswith('附录') and len(normalized)>=3 and title_key(text) in title_key(root_title):
            flush();flush_items();add_record('title_fragment',[(i,line)],title=root_title)
            previous=line;continue
        if re.fullmatch(r'\d+(?:\.\d+)+',text) and pos+1<len(available):
            ni,nl=available[pos+1]
            if nl['bbox'][1]-box[3]<25 and (any(bold_span(s) for s in nl.get('spans',[])) or line.get('ocr')):
                flush();flush_items();consumed.add(ni)
                title=text+' '+nl['text']
                source=[(i,line),(ni,nl)];tail=nl
                for more_id,more in available[pos+2:pos+4]:
                    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 ()/;,:—-]*',more['text']):break
                    if more['bbox'][1]-tail['bbox'][3]>4 or not any(bold_span(s) for s in more.get('spans',[])):break
                    source.append((more_id,more));consumed.add(more_id);title+=' '+more['text'];tail=more
                title=format_term(title)
                events.append((box[1],2,'### '+escape_md(title)))
                add_record('term_heading',source,title=title)
                previous=tail;continue
        if is_heading(line):
            flush();flush_items()
            num=re.match(r'^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)',text)
            depth=min(5,2+num[1].count('.')) if num else 2
            events.append((box[1],2,'#'*depth+' '+escape_md(text)))
            add_record('heading',[(i,line)],depth=depth);previous=line;continue
        marker=list_marker(text)
        if marker and marker['kind'] in ('decimal','alpha') and previous and not barrier:
            prior=previous['text']
            if prior.count('(')+prior.count('（')>prior.count(')')+prior.count('）'):
                marker=None
        if marker:
            flush()
            items.append({**marker,'x':box[0],'lines':[line],'source_lines':[(i,line)]})
            previous=line;continue
        note=re.match(r'^(注\s*\d*|示例\s*\d*)\s*[：:]\s*',text) or re.match(r'^(注\s*\d+|示例\s*\d+)\s+',text)
        if note:
            flush();flush_items()
            current={'kind':'note' if text.startswith('注') else 'example','label':note[1].strip(),'source':[(i,line)]}
            previous=line;continue
        caption=re.match(r'^(?:图|表)\s*(?:[A-Z]\s*\.)?\s*\d+\s*(.*)',text)
        narrative=caption and (re.search(r'[。；]',text) or re.match(r'^(?:(?:确定|给出|定义|规定|说明)了|中|所示|对应|汇总|指示|定义|和|、|\)|）|为|见|是|应|则|给出|列出|描述|显示|用于)',caption[1]))
        if caption and '格式中' in caption[1] and re.search(r'长度(?:为)?\d+字节|使用\s*bit\d',re.sub(r'\s','',caption[1])):narrative=True
        centered=abs((box[0]+box[2])/2-page_width/2)<40
        if caption and not narrative and len(text)<180 and (centered or any(bold_span(s) for s in line.get('spans',[]))):
            flush();flush_items()
            events.append((box[1],2,'<p class="standard-caption">'+rich_line(line)+'</p>'))
            add_record('caption',[(i,line)]);previous=line;continue
        if '::=' in text:
            flush();flush_items()
            code=[(i,line)]
            balance=text.count('{')-text.count('}')
            for ni,nl in available[pos+1:]:
                if is_heading(nl) or re.match(r'^(图|表)\s*\d',nl['text']):break
                if balance<=0 and re.search(r'[\u3400-\u9fff]',nl['text']) and not nl['text'].lstrip().startswith('--'):break
                code.append((ni,nl));consumed.add(ni)
                balance+=nl['text'].count('{')-nl['text'].count('}')
            margin=min(l['bbox'][0] for _,l in code)
            body=[]
            for _,l in code:
                indent=' '*max(0,round((l['bbox'][0]-margin)/(font*.5)))
                value=l['text'].replace('BITSTRING','BIT STRING')
                value=re.sub(r'\)OF',') OF ',value)
                body.append(indent+value)
            events.append((box[1],2,'```asn1\n'+'\n'.join(body)+'\n```'))
            add_record('pseudocode',code);previous=code[-1][1];continue
        if re.match(r'^(?:else\s*if|elseif|if\s*[（(]|end\s*(?:if|for|while)|for\s*[（(a-zA-Z]|return\b|while\s*[（(])',text,re.I):
            flush();flush_items()
            events.append((box[1],2,'<p class="algorithm-line">'+rich_line(line)+'</p>'))
            add_record('pseudocode',[(i,line)]);previous=line;continue
        eq=bool(re.search(r'[=∑∏√∫≠≤≥]',text)) and not re.search(r'[\u3400-\u9fff]',text) and not re.search(r'[。；]$',text)
        if eq and items and previous and box[1]-previous['bbox'][3]<font*.9 and box[0]>=items[-1]['x']-font*.3 and not re.search(r'[。；;]$',previous['text']):eq=False
        if eq:
            flush();flush_items()
            events.append((box[1],2,equation(i,line)))
            add_record('equation',[(i,line)]);previous=line;continue
        if re.match(r'^(?:else\s*if|elseif|if\s*[（(]|end\s*if|for\s*[（(]|return\b|while\s*[（(])',text,re.I):
            flush();flush_items()
            events.append((box[1],2,'```text\n'+text+'\n```'))
            add_record('pseudocode',[(i,line)]);previous=line;continue
        reference=bool(re.match(r'^\[\s*\d+\s*\]|^(?:GB/?T|GB/T|ISO|IEC|IEEE|IETF|ITU[ -])',text))
        # Some embedded PDF fonts extract an ordinary hyphen as U+2043.
        abbreviation=re.match(r'^([A-Za-z0-9][A-Za-z0-9 /⁃-]{0,18})[：:]\s*(\S.*)$',text)
        definition=bool(abbreviation and (abbreviation[1].upper()==abbreviation[1] or re.search(r'[\u3400-\u9fff]',abbreviation[2])))
        symbol_definition=re.match(r'^(.{1,50}?)\s*——+\s*(\S.*)$',text)
        if symbol_definition and not re.search(r'[\u3400-\u9fff]',symbol_definition[1]):definition=True
        gap=box[1]-previous['bbox'][3] if previous else 0
        indent=box[0]-left
        end=previous and bool(re.search(r'[。；;]$',previous['text']))
        # An indented first line, a completed source paragraph, vertical
        # separation, a new reference, or a new glossary entry starts a block.
        starts=reference or definition or gap>font*.8 or (indent>font*1.3 and previous and previous['bbox'][0]<left+font*.8) or end
        if current and current['kind'] in ('note','example') and not reference and not definition:
            initial=current['source'][0][1]
            initial_sizes=[s['size'] for s in initial.get('spans',[]) if s['text'].strip()]
            current_sizes=[s['size'] for s in line.get('spans',[]) if s['text'].strip()]
            if initial_sizes and current_sizes and abs(statistics.median(initial_sizes)-statistics.median(current_sizes))<.5 and gap<font*.9:
                starts=False
        if items:
            if not starts and box[0]>=items[-1]['x']-font*.3:
                items[-1]['lines'].append(line);items[-1]['source_lines'].append((i,line));previous=line;continue
            flush_items()
        if current and starts:flush()
        if current is None:current={'kind':'reference' if reference else 'definition' if definition else 'paragraph','source':[]}
        current['source'].append((i,line))
        previous=line
    flush();flush_items()
    expected={i for i,_ in available}
    assigned=[i for r in ledger if r['page']==page_number for i in r['line_ids']]
    # The caller can split one physical page among adjacent chapter files.
    # Validate this segment rather than all prior records for the same page.
    used=set(assigned)&expected
    if used!=expected:raise ValueError(f'Unassigned paragraph lines on PDF page {page_number}: {sorted(expected-used)}')
    return events
