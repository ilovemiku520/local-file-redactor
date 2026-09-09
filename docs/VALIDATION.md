# 试验与验证记录 / Validation record

[中文 README](../README.md) · [English README](../README.en.md)

记录日期 / Recorded: 2026-09-09. All published files and screenshots use synthetic data.

## 已部署版本 / Deployed application

| Run | Passed | Time | Notes |
|---|---:|---:|---|
| Core + API regression | 36 | 183.73 s | Real OCR and local model included |
| Upload protection + repeated API checks | 7 | 19.92 s | 4 new cases; 3 repeated API cases |
| Lifecycle + repeated API checks | 4 | 20.74 s | 1 new case; 3 repeated API cases |

The above runs cover **41 distinct tests**, not 47 unique cases. Evidence: [regression-summary.json](benchmarks/regression-summary.json).

Coverage includes normalized text offsets, overlapping candidates, ID checks, CSV formula protection, text encodings, CSV delimiters/multiline fields, DOCX/XLSX reconstruction, static formula handling, encrypted storage, password/tamper/matching checks, image OCR, rotated PDF coordinates, local API review/export rules, cancellation/retry/deletion, in-memory uploads and cleanup beyond 200 recent jobs.

## 开源目录验证 / Source repository checks

新增模型准备脚本的路径越界、归档提取与摘要检查用例；通过 pytest 标记区分本地基础测试和需要下载资产的集成测试。开源目录默认测试实测 **33 通过、11 跳过，用时 13.16 秒**。其中跳过项为模型/OCR 集成测试，不能作为通过项计算。

The standalone source layout passed 33 default tests in 13.16 seconds; 11 integration cases were explicitly skipped. Font-dependent cases can be skipped on systems without Microsoft YaHei. CI runs a lightweight subset without model downloads or font-dependent rendering. A committed workflow is not evidence that GitHub-hosted CI has already run.

独立源码目录已实际执行 `scripts/setup.ps1`，完成新建 Python 3.12.10 虚拟环境、锁定依赖安装、SQLite/SSL 检查及前端构建。新环境中的 CI 基础子集实测 **21 通过、23 未选中，用时 3.56 秒**；这是上述用例的子集，不应累加为新的独立测试数量。环境自检还通过了 SQLite 写入与重新打开、图片/PDF 处理、临时后端路由及依赖一致性检查。未向源码目录复制模型。

The setup script was executed in the standalone source folder with a fresh Python 3.12.10 virtual environment. Dependency installation, SQLite/SSL, frontend compilation and the local environment self-check passed. The CI subset then passed 21 tests in 3.56 seconds with 23 deselected. These are a subset of the tests above, not additional unique cases. No model files were copied into the source folder.

The preparation script's integrity verifier was run against the existing official local model/OCR/tokenizer files and passed. Its archive-handling functions were tested with synthetic archives. A second full multi-gigabyte online model download was not performed for the source packaging work.

前端在打包前更新至 Vite 7.3.6 及兼容的 esbuild 修复版本，类型检查与构建再次通过；2026-09-09 的 `npm audit` 返回 0 项已知漏洞。这是当时的前端依赖检查结果，不是整个项目的安全认证。机器可读记录：[source-checks.json](benchmarks/source-checks.json)。

After compatible frontend security updates, Vite 7.3.6 passed type checking and production compilation. `npm audit` reported zero known vulnerabilities on 2026-09-09. This is a point-in-time frontend dependency result, not a security certification of the application. See [source-checks.json](benchmarks/source-checks.json).

## 浏览器与文件成品 / Browser and artifact checks

- Word: actual local model and OCR; 2 review pages; 11 detected candidates.
- Confirmed every page in the browser; exported DOCX, recovery bundle and report.
- Inspected DOCX XML independently and reran OCR on its embedded output image.
- Restored through the browser with the matching output, bundle and demonstration password; the UI reported verified recovery and download.
- Restored bytes matched the original; the output preserved ordinary instructions.

| Artifact | SHA-256 |
|---|---|
| [Synthetic Word input](../examples/input/word.docx) | `6f755e0ae6df3e10c66acdc36813b64f810b7ca9c8e7417e39c59c1d4dfde843` |
| [Redacted DOCX](../examples/output/word.redacted.docx) | `b3653b2d0b5bbc00f618fbb8ac92403e0314d47d97f91d140d31fae9f4eed442` |

## Model smoke test / 模型试运行

Qwen3.5 9B Q4_K_M ran on an RTX 3060 12GB using Ollama 0.33.3 and the CUDA 12 backend. Three short synthetic requests took approximately 11.41 seconds cold and 1.84 / 1.70 seconds warm. These numbers exclude OCR, parsing, review and export. Raw synthetic records: [model-smoke.json](benchmarks/model-smoke.json).

一次包含提示注入文本的样例出现了姓名漏检及组织误报；规则覆盖了其中部分内容，但这不能推断其他信息不会遗漏。没有与 4B 模型做正式质量对照。

A prompt-injection-style synthetic input produced a missed person name and an organization false positive. Rule coverage of part of that sample is not a completeness guarantee. No formal comparison with a 4B model was performed.

## Not established / 尚未建立的结论

No 99% detection claim, zero-leakage guarantee, independent security audit, cross-hardware throughput target or systematic 120-file / 300-page / 3,000-entity benchmark has been established. Contributors should publish new evidence with clear fixtures, annotations, settings and failure cases before changing those claims.
