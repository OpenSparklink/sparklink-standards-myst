#!/usr/bin/env python3
"""Maintain the local acceptance report for the semantic online edition."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def write_report(manifest=None):
    mp=ROOT/'metadata/reading-manifest.json';manifest=manifest or json.loads(mp.read_text());digest=hashlib.sha256(mp.read_bytes()).hexdigest();t=manifest['totals']
    rows=['# 在线规范验收报告','','当前版本采用连续正文和按技术条款组织的网页；封面、印刷目录、页码提示、GB 封面图形和双阅读模式已移除。标准号作为版本识别信息保留，标准引用及技术正文保留原意。','',f"共 {t['documents']} 份标准、{t['chapters']} 个条款页面。原始 PDF 共 {t['pages']} 页，其字形和坐标记录仅用于校对，不作为网页阅读内容发布。",'',
          '| 标准 | 条款页面 | 网页表格 | 原始表格片段 |','|---|---:|---:|---:|']
    for d in manifest['documents']:rows.append(f"| {d['standard']} | {len(d['chapters'])} | {d['native_tables']} | {d.get('source_tables',len(d['tables']))} |")
    rows+=['','## 纸版残留整改','',
           '- 移除 17 个封面及印刷目录入口，包括其中 10 份封面的乱码、GB 图形、ICS／CCS 分类号及出版用排版。',
           '- 移除全部原版阅读和结构化阅读切换、整页 SVG、页码和 PDF 页段提示；正文直接显示。',
           f"- 合回 {t.get('joined_chunk_paragraphs',0)} 处分散在旧分页边界的正文或列表续段，包括词语被拆为‘发／送’、‘数／量’等情况。",
           '- 将 46 个按 PDF 页数划分的续篇重新按条款组织，保留规范编号、附录性质及内容；附录的分行题名归并为完整网页标题。',
           '- 补齐单行报文表；5 个无内部框线或单格表格的网格经过原页复核，依据保存在 reviewed-tables.json。误识别为表题的正文已恢复为段落。',
           f"- 合并 {t.get('joined_table_parts',0)} 个相邻的分页续表片段，去除 {t.get('deduplicated_header_rows',0)} 行经比对相同的重复表头。每个原始单元格保留到网页行列的映射，跨行单元格必须保持连续。",
           f"- 原生数学表达式 {t['native_inline_math']+t['native_display_math']} 处；公式切图引用 {t['remaining_math_images']} 个。分页重复表头已去重，固定比特布局图保留为原始插图，原始单元格逐格核验仍完整覆盖。",
           '- 更新规范概览、技术主题、侧栏层级、全文搜索及图表／公式／条款交叉引用。原有 398 个地址转向对应概览或条款，防止旧链接回到纸版页面。','',
           f"源记录中有 {t.get('omitted_blocks',0)} 个封面排版块明确标记为不发布；附录题名片段归入完整标题。其余源文由类型、源页、原始行、坐标和网页文件追溯。",'',
           '## 当前版本检查','']
    definitions=[('structure-check.json','源文及条款结构'),('native-math-check.json','原生公式'),('heading-check.json','标题'),('browser-check.json','全量浏览器'),('reader-interactions.json','阅读交互'),('corpus-content-check.json','逐段及逐格内容'),('corpus-vector-check.json','数学绘制线条'),('corpus-visual-check.json','源图保真'),('web-edition-check.json','网页残留与交叉引用'),('201-content-check.json','201 字形与源行'),('201-rendered-text-check.json','201 实际渲染文字')]
    for filename,label in definitions:
        p=ROOT/'metadata'/filename;check=json.loads(p.read_text()) if p.exists() else {}
        if check.get('manifest_sha256')!=digest:rows.append(f'- {label}：当前版本待运行。');continue
        issues=len(check.get('issues',[]));details=''
        if filename=='structure-check.json':details=f"{check['documents']} 份标准，{sum(r['source_lines'] for r in check['results'])} 行源文"
        elif filename=='native-math-check.json':details=f"{check['expressions']} 处表达式"
        elif filename=='heading-check.json':details=f"{check['headings']} 个标题及层级"
        elif filename=='browser-check.json':details=f"{check['pages']} 个正文及概览页面，{check['internalLinks']} 个站内链接，{check.get('legacyRedirects',0)} 个旧地址转向；桌面和 390 px 手机布局"
        elif filename=='reader-interactions.json':details=f"{len(check['results'])} 项交互"
        elif filename=='corpus-content-check.json':details=f"{check['blocks']} 个实际渲染内容块，{check['cells']} 个原始表格单元格（含映射到同一表头的分页重复项）；{len(check.get('reviewed_geometry_disagreements',[]))} 处几何模型分歧已逐项视觉确认并绑定哈希"
        elif filename=='corpus-vector-check.json':details=f"{check['blocks']} 个数学／字段图内容块的 {check['rules']} 条线段，与原页核对的转写必须匹配实际原生公式"
        elif filename=='corpus-visual-check.json':details=f"{check['pages']} 个归档原页、{check['figures']} 个发布插图；原页 SVG 的解码差异以 Chromium 复验，插图与 PDF 裁剪逐像素比较"
        elif filename=='web-edition-check.json':details=f"{check['pages']} 个条款页面，{check['targets']} 个技术引用目标，{check['references']} 个实际交叉引用"
        elif filename=='201-content-check.json':details=f"{check['verified_glyph_keys']} 个已核实字形，{check['verified_glyph_occurrences']} 次字符绘制，字符 OCR 兜底 {check['character_ocr_fallbacks']} 处"
        elif filename=='201-rendered-text-check.json':details=f"{check['blocks']} 个正文、列表、定义、引用及公式块"
        rows.append(f'- {label}：{details}；{issues} 个异常。')
    rows+=['','## 核验方法','',
           '中文按内容块核对字符顺序；英文、数字和希腊字母核对大小写与字符数量；普通单元格另核对字符顺序。数学内容核对运算符及 MathML 上下标结构，二维分式、绝对值、集合基数和横线另与源图和显式转写核对。字符清点不能单独证明数学语义。','',
           '每个原始表格单元格独立比对网页中的目标单元格，包括复用的分页表头，并检查行列、合并关系和跨行连续性。逐段和逐格证据分别在 corpus-block-checks.jsonl、corpus-cell-checks.jsonl。','',
           '归档原页的视觉比较用于源文件校对；网页采用适合屏幕的连续排版。插图及原 PDF 自带的栅格代码保留内容，可放大查看。当前页面截图在 metadata/review/web-edition/；历史校对图和早期报告仅作追溯，当前结果以本报告及 reading-manifest.json 为准。','']
    (ROOT/'metadata/html-quality.md').write_text('\n'.join(rows))


if __name__=='__main__':write_report()
