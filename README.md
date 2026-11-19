# SparkLink Docs

星闪国家标准的 MyST 在线文档工程。包含 GB/T 48336 系列 15 份、GB/T 46803 系列 2 份标准，按条款和附录组织为 819 个页面，支持全文搜索、技术引用、原生公式、连续表格和手机阅读。

[在线阅读](https://docs.opensparklink.com/sparklink-standards-myst/) · [验收记录](metadata/html-quality.md) · [维护工具](tools/README.md)

## 本地预览

需要 Node.js 24：

```sh
npm ci
npm run build
npm start
```

打开 <http://127.0.0.1:8800/>。构建产物保存在 `_build/html/`，不提交到 Git。

## 目录

| 目录 | 内容 |
|---|---|
| `standards/` | 规范概览、技术条款、附录 |
| `assets/structured/` | 正文实际引用的 831 张插图及原始栅格代码 |
| `assets/brand/` | 站点标识 |
| `metadata/` | 源文映射、经复核的公式与字形数据、逐段逐格验收依据 |
| `web/`、`styles/` | 阅读交互、搜索辅助、数学字体和排版 |
| `tools/` | 可复用的构建、转换、校验工具，分类见工具说明 |
| `.github/workflows/pages.yml` | 完整构建、浏览器校验、GitHub Pages 部署 |

旧封面、印刷目录、GB 封面图形、页码提示和双阅读模式已从网页移除。标准号、发布日期、规范引用与技术正文保留。表格及公式采用原生内容；固定比特布局图保留原图。339 个续表片段已合并，原始单元格保留到网页行列的映射。

## 校验

```sh
npx playwright install chromium
npm run check:pages
```

`check:pages` 校验所有公式、标题、站内链接、桌面和手机布局，以及搜索、跳转和图片放大。自动选择本机 Chrome 或 Playwright 管理的 Chromium；可通过 `CHROME_PATH` 指定浏览器。

原始 PDF、整页 SVG 和试验性导出物不随公开工程分发。需要逐页视觉复验时，先重新生成源页资产，或设置 `SPARKLINK_AUDIT_ARCHIVE` 指向本地归档，再运行 `SOURCE_PDF_REVIEW=1 npm run check:html` 和 `npm run check:pdf`。已完成的源文比对记录见 `metadata/corpus-*-check.json` 及逐段、逐格 JSONL。

## GitHub Pages

向 `main` 推送后，Actions 自动安装锁定依赖、构建全部 HTML、执行浏览器校验，再发布通过检查的产物。Pages 的发布来源应设为 **GitHub Actions**。

工作流将 `BASE_URL` 设为仓库子路径；自定义字体、图片、搜索、技术引用和旧地址转向均按同一路径处理。本地复现部署环境：

```sh
BASE_URL=/sparklink-standards-myst npm run build
BASE_URL=/sparklink-standards-myst npm start
# 另一终端：
BASE_URL=/sparklink-standards-myst npm run check:pages
```

## 从 PDF 重新生成

源 PDF 来自 [SparkLink 国家标准归档](https://github.com/OpenSparklink/sparklink-national-standards-pdf)，版本和 SHA-256 保存在 `metadata/reading-manifest.json`。

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
export SPARKLINK_LFS_STORAGE=/path/to/lfs-storage
.venv/bin/python -B tools/repair_myst.py --lfs-storage "$SPARKLINK_LFS_STORAGE" --workers 3
npm run check:structure
npm run check:201
npm run build
```

完整的 PDF 复核流程见 [工具说明](tools/README.md)。生成缓存、试验日志和本地归档均由 `.gitignore` 排除。标准正文的权利归原发布方；MyST 和 KaTeX 使用各自的许可证。
