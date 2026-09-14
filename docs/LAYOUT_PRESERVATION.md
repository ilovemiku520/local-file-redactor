# 2.1 排版与字体保留 / Layout and font preservation

修复日期：2026-09-14。此次修复针对 **DOCX→DOCX、XLSX→XLSX 原格式输出**。以前的导出器创建新文档，丢失原始格式；现在在清理后的原 Office XML 结构中替换敏感文字，保留未涉及脱敏的文字和格式属性。

This change fixes native **DOCX→DOCX and XLSX→XLSX** export. The previous exporter created new documents and lost formatting. The new exporter changes selected text within the cleaned original OOXML structure, preserving the surrounding text and formatting properties.

## 保留范围 / Retained features

| 类型 / Type | 保留内容 / Retained |
|---|---|
| Word 字体 | 字体、字号、颜色、粗体、斜体、不同文字片段各自的样式 / Run-specific fonts, sizes, colors, bold and italic |
| Word 布局 | 段落样式、缩进、行距、分节、纸张尺寸、页边距、显式分页 / Paragraph styles, indentation, spacing, sections, paper size, margins and explicit page breaks |
| Word 结构 | 原位置的表格、合并单元格、页眉页脚、脚注尾注、文本框、图片尺寸和锚点 / Tables, merges, headers/footers, notes, text boxes and drawing geometry remain in place |
| Excel 样式 | 单元格字体、填充、边框、对齐、富文本片段、数字与日期格式 / Fonts, fills, borders, alignment, rich-text runs and number/date formats |
| Excel 布局 | 合并区域、行高列宽、冻结窗格、缩放、纸张方向、页边距、打印区域和重复标题 / Merges, dimensions, panes, zoom, orientation, margins, print areas and print titles |
| Excel 内容 | 未改动数字和日期保留原类型；公式使用保存时的缓存值 / Unchanged numbers/dates keep their types; formulas become saved cached values |

敏感文字即使跨越多种字体，也会按字符位置处理。中文宽字符使用 `■`，其他非空白字符使用 `*`，原来的空格、换行和文字片段边界保留。它们是已替换的字符，不是在原文上添加黑色覆盖层。原件仍只能通过对应恢复包和密码恢复。

Redaction spans may cross differently styled runs. Wide characters are replaced with `■`, other non-whitespace characters with `*`; whitespace and run boundaries are retained. The original characters are removed, not hidden behind a visual overlay. Exact-original recovery still requires the matching encrypted bundle and password.

## 安全清理 / Cleanup

- Word：清除批注、删除的修订、编辑身份、隐藏文字、文档属性和外部链接；非安全动态字段保留其显示结果，移除更新指令。
- Excel：排除隐藏工作表，清空隐藏行列的内容但保留位置；清除批注、外部链接、条件格式和数据验证；不保留原共享字符串表中的隐藏或未使用内容。
- 图片：每一张保留图片均进入复核和重新编码，原图、缩略图及不再引用的媒体不会直接复制进成品。
- 只导出允许的关联结构。遇到不支持的对象、外链图片、缺少缓存值的公式或旧版任务，明确要求转换或重新识别。
- 导出校验同时检查 XML 文字和属性；选中的敏感原文若仍出现在格式属性等位置，会阻止导出。

The package is rebuilt from an allow-listed relationship graph. Comments, editing history, document properties, external links, hidden worksheet content and unused shared strings are excluded. Retained images are reviewed and re-encoded. Export validation checks XML text and attributes for selected originals, including residual values inside formatting attributes. Unsupported objects fail explicitly instead of silently falling back to the old layout-losing exporter.

## 验证范围 / Validation scope

新增 [8 项基础排版回归测试与 1 项真实 OCR 集成测试](../backend/tests/test_office_layout.py)，使用合成资料验证：

1. Word 跨字体电话号码遮除，段落、文字样式、页边距、分节、表格和分页属性保持一致，恢复后原件字节一致。
2. Excel 富文本、样式、合并区域、行高列宽、冻结窗格、数字/日期类型、页眉字体及打印配置保持一致。
3. Word 文本框和脚注留在原位置，嵌套文字不会重复计入。
4. 清理 Word 删除修订、隐藏文字、外链、批注、文档属性和自定义附加内容。
5. Excel 共用字符串可以按单元格分别脱敏，不携带未使用的敏感字符串。
6. Excel 公式固定为缓存值后保留原数字格式。
7. Word 图片原有尺寸保留，重新编码后的像素内容可独立读回。
8. 旧版任务明确要求重新分析，防止继续输出丢失排版的成品。
9. 真实 OCR 识别带样式 Word 中的电话号码图片，完成复核、原格式导出、插图二次 OCR 检查与精确恢复，并保留图片尺寸。

2026-09-14 本机默认回归：**41 通过、12 跳过，21.67 秒**。默认不运行需要模型资产的集成用例，跳过项未计入通过数量。在已部署的真实模型/OCR 环境中，另外运行 `test_api.py` 与 `test_office_layout.py --run-integration`：**12 通过，47.31 秒**，其中 8 项基础排版测试与默认回归重复，另有 3 项 API 流程和 1 项真实 OCR 排版测试。本次共验证 45 个不同用例；未重跑其余未改动的图片/PDF 集成用例。

这次新功能验证以 XML 属性比较、独立 Office 库读回、真实插图 OCR 和恢复字节校验为依据，**没有建立 Microsoft Word/Excel 跨版本的像素级视觉验收结论**。新版主页截图来自已运行的 2.1 应用，仅截取主工作区，未发布私人任务名称。

Eight added base tests compare OOXML properties, reopen results with independent Office libraries, and check recovery bytes. A ninth added test uses real OCR on an illustration in a styled Word document. The default regression passed **41 tests with 12 explicitly skipped in 21.67 seconds**. In the deployed model/OCR environment, the API and layout suites passed **12 tests in 47.31 seconds**: eight repeat the base tests, plus three API tests and one real-OCR layout test, for **45 distinct cases** checked overall. Other unchanged image/PDF integration cases were not rerun. This is structural/read-back and OCR validation, not proof of identical rendered pixels across Microsoft Office versions. The refreshed home screenshot shows the running 2.1 workspace, cropped to exclude private task names.

机器可读结果 / Machine-readable results: [layout-checks.json](benchmarks/layout-checks.json). GitHub-hosted results: [Source checks](https://github.com/ilovemiku520/local-file-redactor/actions/workflows/ci.yml).

## 使用与限制 / Usage and limits

- 原格式输出选择 DOCX 或 XLSX；2.0 版本任务需要重新上传识别。
- **复核预览是内容视图，不是 Word/Excel 打印预览。Office 转 PDF 仍为简化版。** 如果需要固定页面外观，请先在 Office 中导出 PDF，再使用本项目的 PDF 脱敏。
- 原字体属性会保留，但使用者电脑缺少原字体时，阅读软件可能替换字体；遮罩字宽不同也可能影响自动换行和分页。
- 条件格式、数据验证、宏、修订历史和外部链接不在保留范围；图表、SmartArt、数学对象、Excel 非图片绘图及旧式页眉图片等需要先转换为静态 PDF。

Choose native DOCX/XLSX output and reanalyze old jobs. Content-review previews and Office-to-PDF conversion remain simplified. Missing fonts and different mask-glyph widths can affect wrapping and pagination. For fixed visual appearance, export PDF using Office first and redact that PDF. Conditional formatting, validations, macros, revision history and external links are intentionally excluded; unsupported complex objects need static-PDF conversion.
