# GB/T 48336.201 原文校对证据

原 PDF SHA-256：`23a176195b4023d57bb91177b47b5f922ad0ead7a20d10c6247019d63ed1b09b`。

`equations-01.png` 至 `equations-22.png` 的左侧是原 PDF 区域，右侧是工程使用的同一原生数学渲染器。覆盖全部 87 个独立公式（含编号 1–79）；源页、区域、LaTeX 与原始行文字见 `equations.json`。按原文核对上下标、括号、大小写和参数，保留原文条件，未按推测改写算法。

`glyph-differences-01.png` 至 `glyph-differences-18.png` 保留 533 个初期字形候选的源轮廓／参考轮廓比较。图中标签是当时的候选，已全部处理；最终字符和图内位置以 `glyph-review-index.json` 为准。完整 1,831 个可见字形的映射、出现页和核验依据在 `../../201-verified-glyphs.json`。下划线与连字符、单撇与双撇、IV 连字和集合差另结合原页位置与字体原始坐标核实。独立参考 PDF 自身的错误 ToUnicode（如督／逗号）不作为最终文字依据。

源页补充图展示封面、信道编码段落、算法、Zadoff–Chu 序列和 TBPEKE／IV 代码。网页按内容重排，原 PDF 页面的精确位置仍可在每章的原版阅读中放大查看。

重新生成公式并排图：

```sh
.venv/bin/python -B tools/review_201_equations.py --lfs-storage /path/to/lfs-storage
node tools/review_201_equations.mjs
```

最终源行核验结果见 `../../201-content-check.json`，浏览器逐段中文顺序及英文、数字、希腊字母清点见 `../../201-rendered-text-check.json`。没有未解决的字形或公式校对项。
