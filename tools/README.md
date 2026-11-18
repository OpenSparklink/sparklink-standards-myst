# 维护工具

只保留工程持续维护需要的入口和支持模块。最初转换、批量 OCR、旧版目录生成、字形猜测及试验性审阅工具已从公开工程移除。

## 构建与阅读

- `build_html.mjs`：严格 MyST 构建，清除过期网页与资源。
- `build_math_styles.mjs`、`math_in_html.mjs`：原生数学与本地字体。
- `postprocess_html.mjs`、`localize_styles.mjs`：发布资源、主标题锚点、引用索引、旧地址转向。
- `serve_html.mjs`、`site_config.mjs`：本地预览、仓库子路径和跨平台浏览器配置。
- `limit_build_network.mjs`：限制大型站点渲染时的请求并发。

## 转换与源文

- `repair_myst.py`：完整 PDF 转换入口。
- `paragraphs.py`、`web_edition.py`、`web_continuations.py`：源文段落、技术条款与续段组织。
- `pdf_tables.py`、`web_tables.py`、`table_audit.py`：表格几何、连续续表及逐格核验。
- `native_math.py`、`math_geometry.py`、`reviewed_math.py`：原生公式、分式横线与已复核转写。
- `recover_201.py`、`pdf_spans.py`、`source_semantics.py`：已验证字形、PDF 字符几何与特殊符号。
- `normalize_captions.py`、`web_references.py`：图表编号、标题和引用目标。
- `source_archive.py`：查找未公开的源页复核资产。

201 的字形依据已冻结为核实过的映射；`201-layout-lines.json` 仅保留词间距和栅格代码识别所需的版面信息，避免继续依赖最初的大型逐字符 OCR 转储。

## 自动校验

常规发布运行 `npm run check:pages`，无需原始 PDF 或本地归档。

需要重新逐段逐格比对原 PDF 时：

```sh
npm run audit:source -- --lfs-storage "$SPARKLINK_LFS_STORAGE"
npm run audit:dom
npm run check:content
npm run check:vectors
npm run check:web
npm run check:201
CAPTURED_DOM=1 npm run check:201-html
```

需要复验所有源页和插图时：

```sh
SOURCE_PDF_REVIEW=1 npm run check:html
npm run check:pdf
npm run audit:visual
npm run audit:svg-browser
npm run audit:visual-resolve
npm run audit:publish
```

源页 SVG 可由转换入口重新生成，或由 `SPARKLINK_AUDIT_ARCHIVE` 指向的私有归档提供。上述工具只在临时校验服务中读取源页，不把它们发布到站点。

## 视觉审阅

`review_web_edition.mjs` 保存桌面和手机的网页样本；`review_reader.mjs` 覆盖复杂公式；`review_corpus_math.py` 与同名 `.mjs` 生成源 PDF 与实际 HTML 对照图。校验输出写入 `metadata/`，中间数据写入被忽略的 `tmp/`。
