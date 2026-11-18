#!/usr/bin/env python3
"""Extract source-verifiable text, tables, diagrams and native mathematics.

The web edition uses semantic clauses. Private PDF-page assets and source
geometry remain available for verification, outside the published reader.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import statistics
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pymupdf as fitz
import yaml
from PIL import Image
from paragraphs import organize,rich_line,text_join,prepare_list_markers
from recover_201 import load_map,decode_span,load_ocr,fallback_lines
from native_math import to_latex,mark_runs,is_separator,source_text as math_source_text
from reviewed_math import apply as reviewed_math,inline as reviewed_inline,prepare_keywords
from math_geometry import fractions,overlines
from pdf_spans import traced_spans
from normalize_captions import normalize as normalize_captions
from pdf_tables import find_tables

ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^(\d+(?:\.[\d]+)*|[A-Z](?:\.\d+)+)\s*(.+)$")
CAPTION = re.compile(r"^(表|图)\s*([A-Z](?:\.)?)?\d+")
MATH_FONT = re.compile(r'^FzBookMaker(?:9Dl|13Dl|14Dl|15Dl)')


def compact(s: str) -> str:
    return re.sub(r"\s+", "", s).replace("．", ".")


def browser_safe_svg(svg: str, page: fitz.Page | None = None) -> str:
    """Browsers mishandle inverted CMYK JPEGs embedded by the SVG exporter."""
    source_images={};by_size={}
    if page is not None:
        for row in page.get_images(full=True):
            source=page.parent.extract_image(row[0])
            if source and source.get('colorspace')==4:
                pix=fitz.Pixmap(page.parent,row[0]);pix=fitz.Pixmap(fitz.csRGB,pix)
                png=pix.tobytes('png')
                source_images[hashlib.sha256(source['image']).digest()]=png
                by_size.setdefault((source['width'],source['height']),[]).append(png)
    def convert(match):
        data=base64.b64decode(match[1])
        with Image.open(io.BytesIO(data)) as image:
            if image.mode != 'CMYK':
                return match[0]
            converted=source_images.get(hashlib.sha256(data).digest())
            candidates=by_size.get(image.size,[])
            if converted is None and len(candidates)==1:converted=candidates[0]
            if converted is None:
                raise ValueError('CMYK image requires its PDF decode information')
        return 'data:image/png;base64,'+base64.b64encode(converted).decode('ascii')
    return re.sub(r'data:image/jpeg;base64,([A-Za-z0-9+/=\s]+?)(?=["\'])',convert,svg)


def escape(s: str) -> str:
    s = html.escape(s, quote=False).replace("\x00", "")
    s = "".join(c for c in s if ord(c) >= 32 or c in "\n\t")
    return re.sub(r"([\\`*_{}\[\]$<>])", r"\\\1", s)


def clean(s: str) -> str:
    return re.sub(r"[\t \u3000]+", " ", s.replace("\u00a0", " ")).strip()


def join_text(parts: list[str]) -> str:
    result = ""
    for text in parts:
        text = clean(text)
        if result and text and re.match(r"[A-Za-z0-9]", text) and re.search(r"[A-Za-z0-9]$", result):
            result += " "
        result += text
    return result


def same_baseline(span,group):
    gap=abs(span['origin'][1]-statistics.median(s['origin'][1] for s in group))
    sizes=[span['size']]+[s['size'] for s in group]
    return gap<3.1 or gap<5.0 and min(sizes)<max(sizes)*.8


def same_cell_baseline(span,group):
    largest=max(s['size'] for s in group)
    baseline=statistics.median(s['origin'][1] for s in group if s['size']>=largest*.94)
    gap=abs(span['origin'][1]-baseline);sizes=[span['size']]+[s['size'] for s in group]
    return gap<3.1 or gap<5.0 and min(sizes)<max(sizes)*.94


def pdf_lines(page: fitz.Page, mapping: dict | None = None) -> list[dict]:
    """Join spans by physical baseline, even when PDF objects split a heading."""
    raw = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
    spans = [s for b in raw["blocks"] if b["type"] == 0 for line in b["lines"] for s in line["spans"]]
    if mapping:spans=traced_spans(page)
    for span in spans:span['source_text']=span['text']
    if mapping:
        for span in spans:span['text']=decode_span(span,mapping)
        overlines(page,spans)
    spans=[s for s in spans if s['text']]
    groups: list[list[dict]] = []
    for span in sorted(spans, key=lambda s: (s["origin"][1], s["bbox"][0])):
        baseline = span["origin"][1]
        if groups and same_baseline(span,groups[-1]):
            groups[-1].append(span)
        else:
            groups.append([span])
    result = []
    for group in groups:
        group.sort(key=lambda s: s["bbox"][0])
        visible=[s for s in group if s['text'].strip()]
        if not visible:continue
        box = fitz.Rect(visible[0]["bbox"])
        pieces = []
        previous = None
        for s in group:
            if previous and s.get('_advance_bbox',s['bbox'])[0] - previous.get('_advance_bbox',previous['bbox'])[2] > 1.5:
                pieces.append(" ")
            pieces.append(s["text"])
            if s['text'].strip():box |= fitz.Rect(s["bbox"])
            previous = s
        text = clean("".join(pieces))
        result.append({"text": text, "bbox": tuple(box), "spans": group, "y": statistics.median(s["origin"][1] for s in visible),"recovered":bool(mapping)})
    return sorted(result, key=lambda l: (round(l["y"], 1), l["bbox"][0]))


def is_heading(line: dict) -> bool:
    text = line["text"]
    if re.search(r'[。；;]$',text) or re.match(r'^\d+[)）]',text):return False
    if compact(text) in {"前言", "引言", "参考文献"} or re.match(r"^附\s*录\s*[A-Z]", text):
        return True
    m = HEADING.match(text)
    if not m or len(text) > 100 or not re.search(r"[A-Za-z\u3400-\u9fff]", m[2]):
        return False
    if re.match(r"^(?:图|表|注|示例)", m[2]):
        return False
    # Bit rows and protocol values are never section headings. At least one
    # span must use the PDF's bold/heading font, or the line must be a short
    # standalone section number followed by a title on the same baseline.
    heading_font = any(s["flags"] & 16 or re.search(r"HT|Hei|Bold|H2-S|Heiti", s["font"], re.I) for s in line["spans"])
    if line.get('recovered') and re.match(r'^\d+(?:\.\d+)*\s+[^0-9]',text) and not re.search(r'[=+∑□]|[。；：;:]$',text) and not any(MATH_FONT.match(s['font']) for s in line['spans']):
        heading_font=True
    return bool(heading_font)


def toc_from_pdf(doc: fitz.Document, pages_lines: list[list[dict]]) -> list[dict]:
    toc = []
    # Bookmarks are used as a title whitelist. Destination Y in some PDFs is
    # incorrect, so the actual text baseline is matched on the indicated page.
    bookmarks = doc.get_toc(simple=False)
    if bookmarks:
        for level, title, page_number, dest in bookmarks:
            if page_number < 1:
                continue
            title = clean(title)
            wanted = compact(title)
            candidates = pages_lines[page_number - 1]
            matches = [l for l in candidates if compact(l["text"]) == wanted]
            if not matches:
                number = re.match(r"^(\d+(?:\.\d+)*)", title)
                matches = [l for l in candidates if number and compact(l["text"]).startswith(number[1]) and compact(re.sub(r"^\d+(?:\.\d+)*", "", title)) in compact(l["text"])]
            y = matches[0]["bbox"][1] if matches else 88.0
            toc.append({"level": level, "title": title, "page": page_number, "y": y, "method": "pdf-bookmark"})
        return toc

    # Read actual TOC rows from geometry; this recovers numeric fragments like
    # '6.' and '1' that pdftotext placed on different lines.
    toc_rows = []
    for p, lines in enumerate(pages_lines[:15], 1):
        if any(compact(l["text"]) == "前言" for l in lines) and p > 3:
            break
        for line in lines:
            text = line["text"]
            match = re.match(r"^(.+?)[.…·]{2,}\s*([0-9ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*$", text)
            if not match:
                continue
            title, printed = clean(match[1]), match[2]
            number = re.match(r"^(\d+(?:\s*\.\s*\d+)*)\s*(.+)", title)
            appendix = re.match(r"^附\s*录\s*([A-Z])", title)
            special = compact(title) in {"前言", "引言", "参考文献"}
            if not (number or appendix or special):
                continue
            if number:
                n = compact(number[1])
                title = n + " " + number[2].strip()
                level = 1 + n.count(".")
            else:
                level = 1
            toc_rows.append({"title": title, "printed": printed, "level": level})

    # Printed page 1 is matched by its real section heading, not a hardcoded
    # offset (front matter lengths differ among standards).
    first_body = next((p for p, lines in enumerate(pages_lines, 1) if p > 3 and any(re.match(r"^1\s*范围$", l["text"]) for l in lines)), 9)
    offset = first_body - 1
    for row in toc_rows:
        printed = row["printed"]
        if not printed.isdigit():
            matches = [(p, l) for p, lines in enumerate(pages_lines, 1) for l in lines if compact(l["text"]) == compact(row["title"]) and p >= 5]
            if not matches:
                continue
            p, line = matches[0]
        else:
            p = int(printed) + offset
            if not 1 <= p <= len(doc):
                continue
            wanted = compact(row["title"])
            matches = [l for l in pages_lines[p - 1] if compact(l["text"]) == wanted]
            if not matches:
                # Annex title is normally split across three centered lines.
                app = re.match(r"^附\s*录\s*([A-Z])", row["title"])
                matches = [l for l in pages_lines[p - 1] if app and compact(l["text"]) == "附录" + app[1]]
            line = matches[0] if matches else {"bbox": (0, 88, 0, 0)}
        toc.append({"level": row["level"], "title": row["title"], "page": p, "y": line["bbox"][1], "method": "pdf-toc-geometry"})
    return toc


def special_toc_201(doc: fitz.Document) -> list[dict]:
    # Verified against source TOC and physical pages. The PDF uses thousands
    # of Type3 fonts and has no usable Unicode mapping. No corrupt text is
    # emitted as Markdown, formula source or MyST citation syntax.
    data = [("1 范围", 1), ("2 规范性引用文件", 1), ("3 术语和定义", 1),
            ("4 符号和缩略语", 3), ("5 系统架构", 5), ("6 物理层", 6),
            ("6.1 一般描述", 6), ("6.2 120 kHz 基础子载波间隔系统", 7),
            ("6.3 灵活带宽", 64), ("6.4 超宽带脉冲系统", 65),
            ("6.5 物理层通用功能", 75), ("6.6 位置测量流程", 82),
            ("6.7 感知测量流程", 94), ("6.8 超宽带脉冲测量流程", 96),
            ("7 数据链路层", 103), ("7.1 概述", 103), ("7.2 媒体接入层", 104),
            ("7.3 链路控制层", 112), ("7.4 管理功能和流程", 125), ("7.5 管理配置", 133),
            ("8 射频要求", 253), ("8.1 应用频段", 253), ("8.2 信道参数配置", 254),
            ("8.3 信道号和基础信道中心频率", 255), ("8.4 发射机要求", 277),
            ("8.5 接收机要求", 283), ("8.6 超宽带脉冲信号射频要求", 286),
            ("9 信息安全", 287), ("9.1 传输安全需求", 287), ("9.2 节点安全需求", 288),
            ("9.3 传输安全机制", 288), ("9.4 超宽带脉冲测量安全", 316),
            ("附录 A（规范性）黑名单管理", 321), ("附录 B（资料性）典型应用场景下安全配置示例", 322),
            ("附录 C（规范性）极化码可靠度排序序列", 323),
            ("附录 D（规范性）业务类型与 AID 映射关系", 326),
            ("附录 E（规范性）上层协议指示与上层协议映射关系", 327),
            ("附录 F（资料性）SLB 车载使用场景", 328),
            ("附录 G（资料性）SLB 连接建立流程示意", 329),
            ("附录 H（资料性）工作带宽和采样速率设置", 331),
            ("附录 I（规范性）mode3 同步节点优先级顺序", 332),
            ("附录 J（资料性）TBPEKE", 333),
            ("附录 K（资料性）被测设备数据包参数双向复合信道计算方法", 334),
            ("附录 L（规范性）节点通信能力", 335),
            ("附录 M（规范性）节点定位和感知能力", 337),
            ("附录 N（规范性）ASN.1 可选信元说明标记", 339)]
    result = [{"level": 1, "title": "前言与引言", "page": 5, "y": 0, "method": "source-visual-review"}]
    for title, page in data:
        result.append({"level": 2 if re.match(r"^\d+\.", title) else 1,
                       "title": title, "page": page + 10, "y": 88.0, "method": "source-toc-ocr-and-visual-review"})
    return result


def rel(path: Path, md: Path) -> str:
    return Path(os.path.relpath(path, md.parent)).as_posix()


def image_md(path: Path, md: Path, alt: str, width: float | None = None, cls: str = "source-region") -> str:
    lines = [f"```{{image}} {rel(path, md)}", f":alt: {alt}", f":class: {cls}"]
    if width:
        lines.append(f":width: {max(50, round(width * 1.4))}px")
    lines.extend(["```", ""])
    return "\n".join(lines)


def merge_axes(values: list[float]) -> list[float]:
    groups = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] < 1.0:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [statistics.mean(g) for g in groups]


def table_html(table, page: fitz.Page, code: str, number: int, caption: str, mapping: dict | None = None,md:Path|None=None,caption_html:str|None=None) -> tuple[str, dict]:
    cells = list(dict.fromkeys(tuple(c) for c in table.cells if c))
    xs = merge_axes([v for c in cells for v in (c[0], c[2])])
    ys = merge_axes([v for c in cells for v in (c[1], c[3])])
    nr, nc = len(ys) - 1, len(xs) - 1
    if nr < 1 or nc < 1 or nr * nc > 12000:
        raise ValueError("unreliable table geometry")
    occupancy = [[0] * nc for _ in range(nr)]
    starts = {}
    span_count = 0
    glyph_images=0
    native_math_cells=0
    source_spans=traced_spans(page)
    glyph_key=lambda span,g:(span['font'],tuple(round(v,3) for v in g['origin']),g['c'])
    expected_glyphs={glyph_key(s,g) for s in source_spans for g in s['_glyphs'] if table.bbox[0]-.3<=g['origin'][0]<table.bbox[2]+.3 and table.bbox[1]<g['origin'][1]-s['size']*.25<table.bbox[3]}
    assigned_glyphs=set()
    for c in cells:
        c0, c1 = [min(range(len(xs)), key=lambda i: abs(xs[i] - v)) for v in (c[0], c[2])]
        r0, r1 = [min(range(len(ys)), key=lambda i: abs(ys[i] - v)) for v in (c[1], c[3])]
        if c1 <= c0 or r1 <= r0:
            continue
        for rr in range(r0, r1):
            for cc in range(c0, c1):
                if occupancy[rr][cc]:
                    raise ValueError("overlapping table cells")
                occupancy[rr][cc] = 1
        cell_spans=[]
        for original_span in source_spans:
            span=dict(original_span)
            right=c[2]+(.3 if abs(c[2]-table.bbox[2])<.1 else -.3)
            chars=[g for g in span['_glyphs'] if c[0]-.3<=g['origin'][0]<right and c[1]<g['origin'][1]-span['size']*.25<c[3]]
            if not chars:continue
            assigned_glyphs.update(glyph_key(span,g) for g in chars)
            span['source_text']=''.join(g['c'] for g in chars);span['text']=span['source_text']
            span['origin']=chars[0]['origin'];span['bbox']=tuple(fitz.Rect(chars[0]['bbox']))
            for g in chars[1:]:span['bbox']=tuple(fitz.Rect(span['bbox'])|fitz.Rect(g['bbox']))
            span['_advance_bbox']=(min(g.get('_advance_bbox',g['bbox'])[0] for g in chars),min(g.get('_advance_bbox',g['bbox'])[1] for g in chars),max(g.get('_advance_bbox',g['bbox'])[2] for g in chars),max(g.get('_advance_bbox',g['bbox'])[3] for g in chars))
            if mapping:span['text']=decode_span(span,mapping)
            if span['text'].strip():cell_spans.append(span)
        cell_spans=fractions(page,cell_spans,c)
        groups=[]
        for span in sorted(cell_spans,key=lambda s:(s['origin'][1],s['bbox'][0])):
            if groups and same_cell_baseline(span,groups[-1]):
                groups[-1].append(span)
            else:groups.append([span])
        native=0
        for group in groups:native+=mark_runs(group)
        if native:native_math_cells+=1
        cell_parts=[rich_line({'text':''.join(s['text'] for s in group),'spans':group,'y':statistics.median(s['origin'][1] for s in group)}) for group in groups]
        content='<br/>'.join(cell_parts)
        has_math=mapping and any(MATH_FONT.match(s['font']) and not s.get('_math_handled') for s in cell_spans)
        if mapping and ('□' in content or has_math):
            cell_image=ROOT/'assets'/'structured'/code/'regions'/f'p{page.number+1:04}-t{number:02}-cell-{r0:03}-{c0:03}.png'
            source_crop(page,c,cell_image)
            content=f'<img src="{rel(cell_image,md)}" width="{max(30,round((c[2]-c[0])*1.4))}" alt="第{page.number+1}页表格{number}第{r0+1}行第{c0+1}列原文符号"/>'
            glyph_images+=1
        attrs = (f' rowspan="{r1-r0}"' if r1-r0 > 1 else "") + (f' colspan="{c1-c0}"' if c1-c0 > 1 else "")
        if attrs:
            span_count += 1
        tag = "th" if r0 == 0 else "td"
        starts[r0, c0] = f"<{tag}{attrs}>{content}</{tag}>"
    # Missing cells are explicit blanks rather than dropped rows/columns.
    lines = [f'<p class="standard-table-caption">{caption_html or html.escape(caption)}</p>', f'<table class="standard-table {"bit-table" if nc > 20 else ""}">']
    for r in range(nr):
        lines.append("<tr>")
        for c in range(nc):
            if (r, c) in starts:
                lines.append(starts[r, c])
            elif not occupancy[r][c]:
                lines.append("<td></td>")
        lines.append("</tr>")
    lines.append("</table>")
    return "\n".join(lines), {"rows": nr, "columns": nc, "cells": len(cells), "merged_cells": span_count,
                                "source_glyphs":len(expected_glyphs),"assigned_glyphs":len(assigned_glyphs&expected_glyphs),"missing_glyphs":[list(k) for k in sorted(expected_glyphs-assigned_glyphs)],
                                "caption": caption, "page": page.number + 1, "bbox": list(table.bbox), "symbol_cell_images":glyph_images,
                                "native_math_cells":native_math_cells,"id": f"{code}-p{page.number+1:04}-t{number:02}"}


def source_crop(page: fitz.Page, box, path: Path) -> None:
    rect = fitz.Rect(box) + (-2, -2, 2, 2)
    rect &= page.rect
    if rect.is_empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image,PngImagePlugin
    key=json.dumps([page.parent.name,page.number,[round(x,3) for x in rect],3])
    if path.exists():
        with Image.open(path) as cached:
            if cached.info.get('source_geometry')==key:return
    pix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=rect,alpha=False)
    info=PngImagePlugin.PngInfo();info.add_text('source_geometry',key)
    Image.frombytes('RGB',(pix.width,pix.height),pix.samples).save(path,pnginfo=info)


def intersects(box, regions: list) -> bool:
    rect = fitz.Rect(box)
    center = (rect.tl + rect.br) / 2
    return any(fitz.Rect(r).contains(center) for r in regions)


def preserve_inline_math(page,lines,asset_dir,md,allow_images=True):
    """Emit editable native math; retain source only for unresolved runs."""
    for li,line in enumerate(lines):
        spans=sorted(line['spans'],key=lambda s:s['bbox'][0]);group=[];number=0
        def flush():
            nonlocal group,number
            value=to_latex(group,force=line.get('_algorithm',False))
            if value:
                group[0]['_html']='$'+value+'$';group[0]['_native_math']=value
                for span in group:span['_math_handled']=True
                for span in group[1:]:span['_html']=''
            elif allow_images and group and any(MATH_FONT.match(s['font']) or '□' in s['text'] for s in group):
                box=fitz.Rect(group[0]['bbox'])
                for span in group[1:]:box|=fitz.Rect(span['bbox'])
                path=asset_dir/'regions'/f'p{page.number+1:04}-inline-{li:03}-{number:02}.png'
                source_crop(page,box,path)
                group[0]['_html']=f'<img class="source-inline-formula" src="{rel(path,md)}" width="{max(8,round(box.width*1.6))}" alt="原文数学表达式"/>'
                for span in group[1:]:span['_html']=''
                number+=1
            group=[]
        for span in spans:
            if span.get('_math_handled'):flush();continue
            decoded=math_source_text(span)
            chinese=bool(re.search(r'[\u3400-\u9fff]',decoded)) and not MATH_FONT.match(span['font'])
            sentence_punctuation=is_separator(span,group)
            if chinese or sentence_punctuation:
                flush()
                if '□' in span['text']:
                    # Unknown prose glyphs stay visible as their exact source
                    # run rather than guessed text. Remaining Chinese keys
                    # have a separate glyph-review ledger.
                    group=[span];flush()
            else:group.append(span)
        flush()


def native_page(page: fitz.Page, lines: list[dict], asset_dir: Path, md: Path, code: str,
                min_y: float, max_y: float, tables_data: list, cache: dict, paragraph_data: list, region_data: list, mapping: dict | None = None,root_title='',page_ocr=None) -> str:
    pnum = page.number + 1
    if pnum not in cache:
        cache[pnum] = find_tables(page,code)
    tables = cache[pnum]
    regions = []
    events = []
    consumed = set()
    prepare_list_markers(lines)
    prepare_keywords(lines,code,pnum)
    reviewed_inline(code,pnum,lines)
    preserve_inline_math(page,lines,asset_dir,md,bool(mapping))
    for n, table in enumerate(tables, 1):
        if table.row_count < 1 or table.col_count < 1 or table.bbox[0] < 20 or table.bbox[2] > page.rect.width - 20:
            continue
        box = table.bbox
        if box[1] < min_y or box[1] >= max_y:
            continue
        captions = [(i,l) for i,l in enumerate(lines) if 0 <= box[1] - l["bbox"][3] < 36 and re.match(r"^表\s*(?:[A-Z]\s*\.)?\s*\d+", l["text"])]
        if (table.row_count==1 or table.col_count==1) and not captions:
            continue
        # Byte/bit-layout figures also contain a complete grid. Their figure
        # caption below the grid identifies them; let the drawing extractor
        # preserve their fixed bit widths and original figure numbering.
        figure_caption=any(0 <= l['bbox'][1]-box[3] < 36 and re.match(r'^图\s*(?:[A-Z]\s*\.)?\s*\d+',l['text']) for l in lines)
        if not captions and figure_caption:
            continue
        caption = captions[-1][1]["text"] if captions else "字段结构"
        if captions:
            consumed.add(captions[-1][0])
        else:
            # A bare continuation marker belongs to the printed table, not
            # to the continuous web prose. Its geometry is still recorded.
            consumed.update(i for i,l in enumerate(lines) if 0 <= box[1]-l['bbox'][3] < 36 and re.fullmatch(r'[（(]\s*续\s*[）)]',l['text']))
        try:
            markup, info = table_html(table, page, code, n, caption,mapping,md,rich_line(captions[-1][1]) if captions else None)
            if hasattr(table,'geometry_review'):info['geometry_review']=table.geometry_review
            if not any(t["id"] == info["id"] for t in tables_data):
                tables_data.append(info)
            events.append((box[1], 1, f"::::{'{'}div{'}'}\n:class: table-scroll\n\n" + markup + "\n\n::::\n"))
        except Exception as error:
            path = asset_dir / "regions" / f"p{pnum:04}-table-{n:02}.png"
            source_crop(page, box, path)
            events.append((box[1], 1, image_md(path, md, caption)))
            tables_data.append({"id": f"{code}-p{pnum:04}-t{n:02}", "page": pnum, "caption": caption, "fallback": str(error), "bbox": list(box)})
        regions.append(box)
        region_data.append({'page':pnum,'kind':'table','bbox':list(box),'file':md.relative_to(ROOT).as_posix()})
        for i in consumed:
            region_data.append({'page':pnum,'kind':'table_caption','bbox':lines[i]['bbox'],'file':md.relative_to(ROOT).as_posix()})

    reviewed_events,reviewed_regions,reviewed_lines=reviewed_math(code,pnum,lines,min_y,max_y,paragraph_data,md.relative_to(ROOT).as_posix())
    events.extend(reviewed_events);regions.extend(reviewed_regions);consumed.update(reviewed_lines)
    # Raster images and vector drawings are located spatially so they appear
    # at their original place among paragraphs, instead of at each page top.
    figure_boxes = []
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.width > 30 and r.height > 4 and min_y <= r.y0 < max_y and not intersects(r, regions):
            figure_boxes.append(r)
    try:
        for box in page.cluster_drawings(x_tolerance=3, y_tolerance=3):
            r = fitz.Rect(box)
            if r.width < 50 or r.height < 22 or r.y0 < max(87, min_y) or r.y1 > min(page.rect.height-50, max_y) or intersects(r, regions):
                continue
            if any((r & t).get_area() / max(1,r.get_area()) > 0.5 for t in figure_boxes):
                continue
            figure_boxes.append(r)
    except Exception:
        pass
    for n, box in enumerate(figure_boxes, 1):
        raster_text=[]
        for item in page_ocr or []:
            b=item['bbox'];cx=(b[0]+b[2])*page.rect.width/2;cy=(b[1]+b[3])*page.rect.height/2
            if box.contains(fitz.Point(cx,cy)):raster_text.append(item['text'])
        code_image=any(re.search(r'ASN[1Il](?:START|STOP)',t) for t in raster_text)
        if len(raster_text)==1 and re.fullmatch(r'\s*--\s*ASN[1Il](?:START|STOP)\s*',raster_text[0]):
            text=raster_text[0].replace('ASNI','ASN1').replace('ASNl','ASN1')
            events.append((box.y0,1,'```asn1\n'+text+'\n```'))
            regions.append(tuple(box));region_data.append({'page':pnum,'kind':'code_marker','bbox':list(box),'file':md.relative_to(ROOT).as_posix()})
            continue
        path = asset_dir / "regions" / f"p{pnum:04}-figure-{n:02}-{int(box.y0)}.png"
        source_crop(page, box, path)
        events.append((box.y0, 1, image_md(path, md, f"{code} PDF 第 {pnum} 页图形，保留原始标注和连线", box.width*(2 if code_image else 1.4),'source-code' if code_image else 'source-figure')))
        regions.append(tuple(box))
        region_data.append({'page':pnum,'kind':'figure','bbox':list(box),'asset':path.relative_to(ROOT).as_posix(),'file':md.relative_to(ROOT).as_posix()})

    def equation(i,line):
        value=to_latex(line['spans'])
        if value and any(op in value for op in ('=',r'\leq',r'\geq')):return '```{math}\n'+value+'\n```'
        if not any(MATH_FONT.match(s['font']) or '□' in s['text'] for s in line['spans']):
            return '<p class="standard-paragraph">'+rich_line(line)+'</p>'
        box=line['bbox']
        path=asset_dir/'regions'/f'p{pnum:04}-equation-{i:03}.png'
        source_crop(page,(max(30,box[0]-6),box[1]-3,min(page.rect.width-25,box[2]+6),box[3]+3),path)
        return image_md(path,md,f'{code} 第 {pnum} 页公式 {i}',box[2]-box[0],'source-equation')
    events.extend(organize(lines,page_number=pnum,min_y=min_y,max_y=max_y,page_height=page.rect.height,page_width=page.rect.width,
                          excluded=consumed,regions=regions,is_heading=is_heading,escape_md=escape,
                          equation=equation,breaks=[e[0] for e in events],ledger=paragraph_data,root_title=root_title))
    events.sort(key=lambda e: (round(e[0], 1), e[1]))
    return "\n\n".join(event[2].strip() for event in events)


def chapters_from_toc(toc: list[dict], count: int) -> list[dict]:
    tops = [dict(x) for x in toc if x["level"] == 1]
    tops.sort(key=lambda x: (x["page"], x["y"]))
    starts = [{"title": "封面与目录", "page": 1, "y": 0.0, "level": 1, "method": "all-page-coverage"}] + tops
    dedup = []
    for item in starts:
        if not dedup or compact(dedup[-1]["title"]) != compact(item["title"]):
            dedup.append(item)
    result = []
    for index, item in enumerate(dedup):
        end = dedup[index + 1] if index + 1 < len(dedup) else {"page": count + 1, "y": 0}
        last_page = end["page"] - (1 if end["y"] == 0 else 0)
        length = last_page - item["page"] + 1
        # Long chapters are subdivided by actual subheadings, then by bounded
        # page groups if one subsection is itself very long.
        children = []
        if length > 18:
            children = [dict(x) for x in toc if x["level"] == 2 and (item["page"],item["y"]) < (x["page"],x["y"]) < (end["page"],end["y"])]
        cuts = [item] + sorted(children, key=lambda x: (x["page"],x["y"]))
        expanded = []
        for j, cut in enumerate(cuts):
            next_cut = cuts[j+1] if j+1 < len(cuts) else end
            expanded.append(cut)
            for start in range(cut["page"]+16, next_cut["page"], 16):
                expanded.append({"title": f"{cut['title']}（续，PDF 第 {start} 页起）", "page": start, "y": 0.0,
                                 "level": cut["level"] + 1, "method": "bounded-chapter-part"})
        for j, cut in enumerate(expanded):
            next_cut = expanded[j+1] if j+1 < len(expanded) else end
            cut["end_page"], cut["end_y"] = next_cut["page"], next_cut["y"]
            cut["parent_title"] = item["title"]
            result.append(cut)
    return result


def coherent_headings(text: str, root_title: str = '', titles: dict | None = None) -> str:
    """Start each tab at depth two and do not skip HTML heading levels."""
    depth = 1
    output = []
    root_number=re.match(r'^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)\b',root_title)
    base=root_number[1].count('.') if root_number else 0
    titles=titles or {}
    for line in text.splitlines():
        if line.startswith(":::::{tab-item}"):
            depth = 1
        match = re.match(r"^(#{2,6}) (.+)$", line)
        if match:
            heading=match[2]
            if compact(heading)==compact(root_title):continue
            number=re.match(r'^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)\b',heading)
            wanted=max(2,min(6,number[1].count('.')-base+1)) if number else 2
            if wanted>depth+1 and number:
                parts=number[1].split('.')
                for missing_depth in range(depth+1,wanted):
                    prefix='.'.join(parts[:missing_depth+base])
                    output.extend(['#'*missing_depth+' '+escape(titles.get(prefix,prefix)), ''])
            depth = wanted
            line = "#" * depth + " " + match[2]
        output.append(line)
    return "\n".join(output) + "\n"


def semantic_markup(text):
    """Use native MyST nodes: HTML conversion drops p/list classes and dl."""
    def paragraph(match):
        cls,body=match.groups()
        return f'\n\n:::{{div}}\n:class: {cls}\n\n<p>{body}</p>\n\n:::\n\n'
    text=re.sub(r'<p class="(standard-(?:paragraph|reference|caption|table-caption)|source-page-label|algorithm-line)">(.*?)</p>',paragraph,text,flags=re.S)
    def definition(match):
        term,body=match.groups()
        term=html.unescape(term) if '$' in term or '<' in term else escape(html.unescape(term))
        return f'\n\n:::{{div}}\n:class: standard-definitions\n\n{term}\n: {body}\n\n:::\n\n'
    text=re.sub(r'<dl class="standard-definitions"><dt>(.*?)</dt><dd>(.*?)</dd></dl>',definition,text,flags=re.S)
    depth=0;start=None;replacements=[]
    for match in re.finditer(r'</?(?:ol|ul)\b[^>]*>',text):
        closing=match[0].startswith('</')
        if not closing:
            if depth==0:start=match.start()
            depth+=1
        else:
            depth-=1
            if depth==0 and start is not None:
                replacements.append((start,match.end()));start=None
    for start,end in reversed(replacements):
        text=text[:start]+'\n\n:::{div}\n:class: standard-list-block\n\n'+text[start:end]+'\n\n:::\n\n'+text[end:]
    return text


def normalize_blank_lines(text):
    """Keep generated Markdown compact without touching fenced code/math."""
    output=[];fence=None
    for line in text.splitlines():
        marker=re.match(r'^(`{3,}|~{3,})',line)
        if marker:
            if fence is None:fence=marker[1]
            elif marker[1][0]==fence[0] and len(marker[1])>=len(fence):fence=None
        if not line.strip() and fence is None and output and not output[-1].strip():continue
        output.append(line.rstrip())
    return '\n'.join(output).strip()+'\n'


def generate_document(row: dict, storage: str) -> dict:
    code = Path(row["source"]).stem.split("_",1)[0]
    h = row["sha256"]
    pdf = Path(storage)/"objects"/h[:2]/h[2:4]/h
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != h:
        raise RuntimeError(f"source hash mismatch: {code}")
    doc = fitz.open(pdf)
    if len(doc) != int(row["pages"]):
        raise RuntimeError(f"source page mismatch: {code}")
    broken = code == "GBT-48336.201-2026"
    mapping=load_map() if broken else None
    ocr=load_ocr() if broken else {}
    lines = [fallback_lines(page,pdf_lines(page,mapping),ocr[page.number+1]) if broken else pdf_lines(page) for page in doc]
    toc = special_toc_201(doc) if broken else toc_from_pdf(doc, lines)
    heading_titles={}
    for page_lines in lines:
        for line in page_lines:
            if is_heading(line):
                n=re.match(r'^(\d+(?:\.\d+)*|[A-Z](?:\.\d+)+)\b',line['text'])
                if n:heading_titles.setdefault(n[1],line['text'])
    if broken:
        for entry in toc:
            candidates=lines[entry['page']-1]
            match=[l for l in candidates if compact(l['text'])==compact(entry['title'])]
            number=re.match(r'^(\d+(?:\.\d+)*)\s',entry['title'])
            if not match and number:match=[l for l in candidates if re.match(re.escape(number[1])+r'\s',l['text']) and len(l['text'])<100]
            if match:entry['y']=match[0]['bbox'][1]
    if not any(re.match(r"^1\s*范围", x["title"]) for x in toc):
        raise RuntimeError(f"failed to locate true contents: {code}")
    chapters = chapters_from_toc(toc, len(doc))
    md_dir = ROOT / Path(row["path"]).parent
    assets = ROOT / "assets" / "structured" / code
    (assets / "pages").mkdir(parents=True, exist_ok=True)
    (assets / "regions").mkdir(parents=True, exist_ok=True)
    page_meta = []
    for p, page in enumerate(doc,1):
        path = assets / "pages" / f"page-{p:04d}.svg"
        if not path.exists():
            path.write_text(browser_safe_svg(page.get_svg_image(text_as_path=True),page), encoding="utf-8")
        page_meta.append({"page":p,"asset":path.relative_to(ROOT).as_posix(),"width":page.rect.width,"height":page.rect.height,
                          "blank":not page.get_text().strip() and not page.get_images() and not page.get_drawings()})
    tables = []
    paragraph_data=[]
    region_data=[]
    table_cache = {}
    paths = set()
    for i, chapter in enumerate(chapters,1):
        slug = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-") + f"-{i:02d}"
        md = md_dir / f"{slug}.md"
        paths.add(md)
        route = re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-") + f"-{i:02d}"
        chapter.update({"path":md.relative_to(ROOT).as_posix(),"slug":route})
        title = chapter["title"]
        last = min(len(doc),chapter["end_page"] - (1 if chapter["end_y"] == 0 else 0))
        source_pages = list(range(chapter["page"],last+1))
        front = yaml.safe_dump({"title":title,"short_title":title,"description":f"{row['standard']}，{title}",
                                "numbering":{"headings":False,"figure":False,"table":False,"equation":False,"subequation":False}},allow_unicode=True,sort_keys=False).strip()
        out = ["---", front, "---", "", f"# {title}", "", f"{row['standard']} · PDF 第 {chapter['page']}-{last} 页", "",
               "::::::{tab-set}", "", ":::::{tab-item} 原版阅读", "", "原版页保留 PDF 的字形、表格、公式、图注和页码，可点击图像放大。", ""]
        for p in source_pages:
            blank = page_meta[p-1]["blank"]
            out.extend([f"<!-- page: {p} -->", "", f'<p class="source-page-label">PDF 第 {p} 页'+("（原文空白页）" if blank else "")+'</p>', "",
                        image_md(ROOT/page_meta[p-1]["asset"],md,f"{row['standard']} PDF 第 {p} 页原版矢量页面",cls="pdf-facsimile")])
        out.extend([":::::", "", ":::::{tab-item} 结构化阅读", ""])
        if broken:out.extend([':::{note}','本标准文字与特殊符号已依据原 PDF 字形校验恢复；原版阅读保留逐页对照。',':::',''])
        previous_native_index=None
        for p in source_pages:
            page = doc[p-1]
            min_y = chapter["y"] if p == chapter["page"] else 0.0
            max_y = chapter["end_y"] if p == chapter["end_page"] else page.rect.height
            if p in (3,4):
                if p==3:
                    out.extend(['## 目录',''])
                    for item in toc:
                        out.append('  '*(min(3,item['level'])-1)+'- '+escape(item['title'])+f"（PDF 第 {item['page']} 页）")
            else:
                before=len(paragraph_data)
                prior_records=[r for r in paragraph_data if r['page']==p-1 and r.get('file')==md.relative_to(ROOT).as_posix()]
                previous_record=max(prior_records,key=lambda r:r['bbox'][3],default=None)
                content=native_page(page,lines[p-1],assets,md,code,min_y,max_y,tables,table_cache,paragraph_data,region_data,mapping,title,ocr.get(p,[]))
                for record in paragraph_data[before:]:record['file']=md.relative_to(ROOT).as_posix()
                first_record=min(paragraph_data[before:],key=lambda r:r['bbox'][1],default=None)
                if previous_native_index is not None and previous_record and first_record and first_record['kind']=='paragraph' and previous_record['kind'] in ('paragraph','list_item'):
                    ended=bool(re.search(r'[。；;.!?！？：:]$',previous_record['source_text']))
                    left=min((l['bbox'][0] for l in lines[p-1] if len(l['text'])>20 and not re.match(r'^GB\s*/?\s*T',l['text'])),default=first_record['bbox'][0])
                    is_continuation=first_record['bbox'][0]<left+6 if previous_record['kind']=='paragraph' else abs(first_record['bbox'][0]-previous_record['bbox'][0]-20)<7
                    first_paragraph=re.match(r'<p class="standard-paragraph">((?:(?!</p>).)*)</p>\s*',content,re.S)
                    previous_content=out[previous_native_index]
                    close=previous_content.rfind('</p>')
                    suffix=previous_content[close+4:].strip() if close>=0 else 'invalid'
                    valid_suffix=not suffix or bool(re.fullmatch(r'(?:\s*</(?:li|ul|ol)>)+',suffix))
                    if not ended and is_continuation and first_paragraph and close>=0 and valid_suffix:
                        out[previous_native_index]=text_join([previous_content[:close],first_paragraph[1]])+previous_content[close:]
                        content=content[first_paragraph.end():]
                        first_record['continuation_of']={'page':previous_record['page'],'line_ids':previous_record['line_ids']}
                        previous_record['continues_on_page']=p
                out.extend([f"<!-- structured page: {p} -->", "",content, ""])
                previous_native_index=len(out)-2
        out.extend([":::::", "", "::::::", ""])
        rendered='\n'.join(out)
        prefix,rest=rendered.split(':::::{tab-item} 原版阅读\n',1)
        original,rest=rest.split(':::::{tab-item} 结构化阅读\n',1)
        native,_=rest.rsplit(':::::\n\n::::::',1)
        rendered=prefix+':::::{tab-item} 结构化阅读\n'+native+':::::\n\n:::::{tab-item} 原版阅读\n'+original+'::::::\n'
        rendered=semantic_markup(coherent_headings(rendered,title,heading_titles))
        rendered=normalize_captions(rendered,md.relative_to(ROOT).as_posix(),tables,paragraph_data,region_data)
        md.write_text(normalize_blank_lines(rendered),encoding="utf-8")
    index = md_dir / f"{code}.md"
    paths.add(index)
    index_front = {"title": row["standard"] + " " + Path(row["source"]).stem.split("_",1)[1].replace("-"," "),
                   "short_title":row["standard"]}
    output = ["---",yaml.safe_dump(index_front,allow_unicode=True,sort_keys=False).strip(),"---","",f"# {index_front['title']}","",
              f"共 {len(doc)} 页。各章节提供原版矢量阅读与结构化阅读，原文表号和附录编号保留。", "", "## 章节", ""]
    for chapter in chapters:
        output.append(f"- [{chapter['title']}]({Path(chapter['path']).name})")
    output.extend(["", "## 来源与追溯", "", f"源文件：`60_national_standards/{row['source']}`", "",f"SHA-256：`{h}`", ""])
    index.write_text("\n".join(output),encoding="utf-8")
    # These files were generated by the earlier converter and are recoverable
    # in Git. Remove only obsolete Markdown in this exact standard directory.
    for md in md_dir.glob("*.md"):
        if md not in paths:
            md.unlink()
    paragraph_path=ROOT/'metadata'/'paragraphs'/f'{code}.json'
    paragraph_path.parent.mkdir(parents=True,exist_ok=True)
    paragraph_path.write_text(json.dumps({'code':code,'blocks':paragraph_data,'regions':region_data,'kinds':dict(Counter(p['kind'] for p in paragraph_data))},ensure_ascii=False,indent=2)+'\n')
    chapter_text='\n'.join((ROOT/c['path']).read_text() for c in chapters)
    return {"code":code,"standard":row["standard"],"source":row["source"],"sha256":h,"pages":len(doc),"index":index.relative_to(ROOT).as_posix(),
            "family":row["family"],"chapters":chapters,"toc":toc,"page_assets":page_meta,"tables":tables,"broken_mapping":broken,
            "native_tables":sum(1 for t in tables if "fallback" not in t),"merged_cells":sum(t.get("merged_cells",0) for t in tables),
            "table_fallbacks":sum(1 for t in tables if "fallback" in t),"paragraph_blocks":len(paragraph_data),
            "joined_page_paragraphs":sum('continuation_of' in p for p in paragraph_data),
            "native_inline_math":len(re.findall(r'\$[^$\n]+\$',chapter_text)),
            "native_display_math":len(re.findall(r'^```\{math\}',chapter_text,re.M)),
            "native_math_cells":sum(t.get('native_math_cells',0) for t in tables),
            "table_geometry":"pdf-vector-lines",
            "remaining_math_images":len(re.findall(r'(?:inline-\d{3}-\d{2}|equation-\d{3})\.png',chapter_text)),
            "paragraph_kinds":dict(Counter(p['kind'] for p in paragraph_data)),"paragraph_ledger":paragraph_path.relative_to(ROOT).as_posix()}


def write_project(results: list[dict]):
    from web_edition import upgrade_documents,write_publication
    results=upgrade_documents(results)
    data=write_publication(results)
    manifest_path=ROOT/'metadata/manifest.tsv'
    with manifest_path.open() as source:
        reader=csv.DictReader(source,delimiter='\t');fields=reader.fieldnames
        originals={r['standard']:r for r in reader if r['kind']=='standard'}
    with manifest_path.open('w') as output:
        writer=csv.DictWriter(output,fieldnames=fields,delimiter='\t',lineterminator='\n');writer.writeheader()
        for d in results:
            row=originals[d['standard']];row.update(path=d['index'],status='原生网页；按技术条款组织')
            writer.writerow(row)
            for i,c in enumerate(d['chapters'],1):
                writer.writerow({'standard':d['standard'],'family':d['family'],'source':d['source'],'path':c['path'],'kind':f'chapter-{i}'})
    from quality_report import write_report
    write_report(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lfs-storage",type=Path,default=Path("/private/tmp/sparklink-lfs-storage"))
    parser.add_argument("--workers",type=int,default=3)
    parser.add_argument("--only",default="")
    args = parser.parse_args()
    rows = [r for r in csv.DictReader((ROOT/"metadata/manifest.tsv").open(),delimiter="\t") if r["kind"] == "standard"]
    if args.only:
        rows = [r for r in rows if args.only in r["standard"]]
        if not rows:parser.error(f"No standard matches --only {args.only!r}")
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(generate_document,row,str(args.lfs_storage)):row for row in rows}
        for future in as_completed(futures):
            result=future.result()
            results.append(result)
            print(f"{result['code']}: {result['pages']} pages, {len(result['chapters'])} chapters, {result['native_tables']} native tables, {result['table_fallbacks']} table fallbacks",flush=True)
    results.sort(key=lambda r:r["code"])
    from web_edition import upgrade_documents
    results=upgrade_documents(results)
    if args.only:
        (ROOT/"tmp").mkdir(exist_ok=True)
        (ROOT/"tmp"/f"sample-{args.only}.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    else:
        write_project(results)
        print(json.dumps({"documents":len(results),"pages":sum(r["pages"] for r in results),"tables":sum(r["native_tables"] for r in results)},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
