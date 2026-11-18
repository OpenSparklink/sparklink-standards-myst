# 内容依据与验收记录

- `reading-manifest.json`、`manifest.tsv`：标准版本、源 PDF 哈希、条款页面与表格映射。
- `paragraphs/`：源行、坐标、段落类型与网页去向；不发布的纸版内容明确标记。
- `reviewed-math*`、`201-reviewed-content.yml`、`reviewed-tables.json`：经原页复核的转写和表格网格。
- `201-font-map.json`、`201-verified-glyphs.json`、`math-glyph-map.json`：核实过的字形映射。
- `201-layout-lines.json`：词间距和原始栅格代码识别所需的精简版面信息。
- `corpus-*-checks.jsonl`：逐段、逐格比对证据。
- `*-check.json`、`reader-interactions.json`、`pdf-html-comparison.json`：自动验收结果。
- `html-quality.md`：验收方法、覆盖范围和已完成结果。
- `review/`：当前网页及特殊公式、表格的视觉依据。

PDF 来源和版本以清单中的 SHA-256 为准。源 PDF、整页 SVG、最初 OCR 转储及旧版导出物不属于站点运行依赖，不进入公开仓库。重新做源页像素复验需要原 PDF 和生成的源页资产。
