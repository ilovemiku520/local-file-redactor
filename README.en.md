<div align="center">

# Local File Redactor

**Keep documents local. Review sensitive content. Recover originals with encryption.**

[简体中文](README.md) | **English**

Windows · Python 3.12 · React 19 · Qwen3.5 9B · PP-OCRv5

[![Source checks](https://github.com/ilovemiku520/local-file-redactor/actions/workflows/ci.yml/badge.svg)](https://github.com/ilovemiku520/local-file-redactor/actions/workflows/ci.yml)

[Quick start](#quick-start) · [Requirements](#requirements) · [Observed results](#observed-results) · [Source layout](#source-layout)

</div>

Local File Redactor is an open-source document redaction application designed for Chinese documents. It combines a **local language model, OCR, deterministic rules and human page review** to find and remove names, phone numbers, email addresses, IDs, bank accounts, addresses and custom sensitive terms. It handles Word, Excel, PDF, text, CSV and common image formats, with password-encrypted recovery bundles for exact restoration of original files.

This repository contains the main backend/frontend code, setup scripts, synthetic examples, real UI screenshots and validation records. **Model/OCR weights, Python/Ollama executables, private jobs and real user documents are excluded.** Assets are downloaded separately on your computer. Initial setup needs internet access; document processing uses local services once setup is complete.

![Home: multi-format imports and local processing settings](docs/assets/ui-home.png)

## 2.1 formatting fix

Native Word/Excel export now edits the original OOXML structure instead of creating a new document. Sensitive text spanning multiple styled runs is removed character by character without flattening the paragraph or worksheet. Re-upload and analyze old jobs to use this export path. See [formatting validation](docs/LAYOUT_PRESERVATION.md).

## Features

| Capability | Behavior |
|---|---|
| Multiple input/output formats | DOCX→DOCX/PDF, XLSX→XLSX/PDF, PDF→PDF, TXT→TXT, CSV→CSV and supported image conversions |
| Local detection | Qwen3.5 9B semantic extraction, PP-OCRv5 Chinese OCR, rules and dictionaries; explicit rules-only mode is also available |
| Human review | Page previews, keep-original choices, additional sensitive terms and manual image rectangles; every page must be confirmed |
| Pixel redaction | Rewrites pixels in PDFs, images and Office illustrations; rebuilt PDFs omit the original text layer and annotation objects |
| Preserve native Office formatting | Edits DOCX/XLSX in place, preserving fonts, sizes, colors, paragraphs, merged tables, headers/footers, row/column dimensions and print settings |
| Encrypted recovery | Every supported format can produce a `.rdvault` bundle for byte-exact original recovery with the matching output and password |
| Local data protection | AES-GCM job storage, Windows DPAPI key protection, bounded in-memory uploads, one-time local pairing and CSRF checks |
| Job lifecycle | Sequential batch queue, cancel, retry, deletion, expired-job cleanup and revision-bound export validation |

> Automated detection is not a zero-leakage guarantee. Review every page, especially handwriting, stamps, faces, QR codes, low-quality text and complex layouts. Native DOCX/XLSX exports retain formatting. Content previews and Office-to-PDF exports remain simplified. Mask glyph widths and different readers may affect wrapping; pixel-identical pagination is not promised. Recovery restores the original file without merging later edits.

## Supported formats

| Input | Output | Notes |
|---|---|---|
| `.txt` | `.txt` | UTF-8, BOM-marked UTF-16, GB18030 and related input handling; UTF-8 output |
| `.csv` | `.csv` | Preserves delimiters and multiline fields; protects formula-like cells; UTF-8 with BOM output |
| `.docx` | `.docx` / `.pdf` | Preserves native DOCX fonts, paragraphs, sections, tables, headers/footers, notes and text-box locations; optional PDF is simplified |
| `.xlsx` | `.xlsx` / `.pdf` | Preserves XLSX styles, merges, row/column sizes, freeze panes, number formats and print settings; formulas become cached values |
| `.pdf` | `.pdf` | 300 DPI rendering, OCR/native-text positioning, pixel redaction and image-only PDF reconstruction |
| `.png` / `.jpg` / `.jpeg` / `.webp` / `.bmp` | Any listed image format | Single-frame images, pixel redaction and fresh encoding; PNG by default |

Legacy DOC/XLS, PPT/PPTX, macro-enabled files and multi-frame images are not supported. Office charts, SmartArt, math/embedded objects, Excel non-image drawings/legacy header pictures, external data and formulas without cached values require prior conversion to static content. Hidden content is not copied directly into the output. See [architecture and limitations](docs/ARCHITECTURE.md).

## UI preview

### Review and export

Red rectangles indicate selected image regions; the right panel lists candidates and their sources. Review and recovery screenshots show the 2.0 synthetic Word example, reviewing text and illustrations separately. The home screenshot above has been refreshed for 2.1.

![Page review, candidates and completed DOCX export](docs/assets/ui-review.png)

### Restore the original

Select the **unchanged redacted file + matching recovery bundle + export password**. Incorrect passwords, modified outputs and mismatched bundles are rejected.

![Encrypted original-file recovery](docs/assets/ui-restore.png)

The README is bilingual. The application UI is currently Chinese.

## Observed results

The images and downloadable output are **actual synthetic results retained from version 2.0**, illustrating detection, image redaction and recovery. See the [2.1 validation record](docs/LAYOUT_PRESERVATION.md) for native formatting checks. The right image was extracted directly from the exported DOCX; no additional masking or visual retouching was applied. OCR currently creates line-level boxes, so an entire detected line may be covered.

| Synthetic input | Exported redacted illustration |
|---|---|
| ![Synthetic source image](examples/input/image.png) | ![Actual redacted illustration](docs/assets/redacted-example.png) |

- [Original Word example](examples/input/word.docx) · [Redacted DOCX](examples/output/word.redacted.docx)
- [Synthetic inputs](examples/input) include TXT, CSV, DOCX, XLSX, PNG and a scanned PDF.
- The Word example produced **2 review pages and 11 candidates**, covering body text, a table, a header and an illustration.
- Independent output XML inspection and a second OCR pass on the illustration found none of the selected names, phone numbers, email addresses or address fragments; ordinary instructions remained.
- Recovery produced the same SHA-256 as the original. Reports, incorrect passwords, output matching and revision checks were also exercised.

| Validation | Observed outcome | Scope |
|---|---|---|
| 2.1 default regression (2026-09-14) | 41 passed, 12 skipped | Includes eight new base layout tests; model/OCR integration tests skipped by default |
| 2.1 deployed-environment checks (2026-09-14) | 12 passed | Eight repeated base layout tests, three real API tests and one real-OCR layout/recovery test; 45 distinct cases overall |
| 2.0 historical regression (2026-09-09) | 41 distinct tests passed | Includes real local model/OCR, recovery, upload protection, rotated PDFs and lifecycle cleanup; not all rerun |
| GitHub Actions | Backend and frontend jobs passed | Windows backend tests/publication audit and Linux frontend build; no model downloads |
| Browser flow | Word detection, review, export and recovery succeeded | Synthetic data and actual Chinese UI interaction |
| Short 9B model calls | About 11.41 s cold; 1.84 / 1.70 s warm | Three synthetic inputs; model-call time only, not whole-document latency |
| Offline environment reconstruction | Relocated Python plus a fresh virtual environment passed | Same Windows machine, not a cross-hardware acceptance test |

These are functional checks and small smoke tests, **not an accuracy or zero-leakage benchmark**. No systematic benchmark of 120 files, 300 pages and 3,000 annotated entities has been completed, and no 99% detection claim is made. See the [2.1 layout validation](docs/LAYOUT_PRESERVATION.md), [2.0 validation notes](docs/VALIDATION.md) and [2.1 machine-readable summary](docs/benchmarks/layout-checks.json).

## Requirements

This release targets **single-user Windows x64 deployment**. The implementation depends on Windows DPAPI and the Microsoft YaHei system font. macOS/Linux support has not been implemented.

| Component | Requirement or guidance | Validated configuration |
|---|---|---|
| OS | Windows 10 22H2 or later / Windows 11, 64-bit | Windows x64 |
| Python | Full official Python 3.12 x64, including SQLite, SSL and venv | 3.12.10 |
| Node.js | Node.js 22 for setup/frontend builds; unnecessary to serve an already built UI | 22.17.1 |
| GPU | A 12GB VRAM-class NVIDIA GPU is recommended for the 9B model | RTX 3060 12GB, driver 576.02, CUDA 12 backend |
| RAM | At least 16GB recommended; 32GB for larger documents; not a measured hard minimum | No multi-machine memory benchmark |
| Storage | Reserve at least 20GB for runtimes, assets, dependencies and jobs | Qwen model data is about 6.59GB, plus OCR and runtimes |
| Chinese font | `C:/Windows/Fonts/msyh.ttc` | Microsoft YaHei |
| Local ports | 8080 for the app and 11434 for the model; free of other instances | Loopback bindings only |

The project pins Ollama **0.33.3**, Qwen3.5 **9B Q4_K_M**, PaddleOCR **3.3.2** and PaddlePaddle **3.2.2**. CPU inference and other GPUs may be slower and have not received full acceptance testing; the launcher currently selects CUDA 12. See [Ollama's Windows documentation](https://docs.ollama.com/windows) for its general platform requirements.

## Quick start

### 1. Get the source and install dependencies

Clone this repository or use GitHub's **Code → Download ZIP**, extract it, and open PowerShell in the repository root:

```powershell
git clone https://github.com/ilovemiku520/local-file-redactor.git
cd local-file-redactor
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script uses Python Launcher's `py -3.12`, creates `.venv`, installs locked dependencies, runs `npm ci` and builds the UI. Without Python Launcher, supply the full Python executable path:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -PythonExe 'D:\Python312\python.exe'
```

Use a complete [official Python installation](https://www.python.org/downloads/release/python-31210/). Copying `python.exe` alone can omit dependencies such as `sqlite3.dll`. Install [Node.js](https://nodejs.org/en/download) first and make sure `npm.cmd` is available.

### 2. Download model assets separately

Exit other Ollama instances using port 11434, then run:

```powershell
.\.venv\Scripts\python.exe -I scripts\prepare_models.py
```

This downloads Ollama, PP-OCRv5, the tokenizer and `qwen3.5:9b` into the Git-ignored `runtime/` directory. **No documents are read or uploaded.** It validates the official Ollama archive, OCR assets, tokenizer, model manifest and blobs using SHA-256. See [models.lock.json](models.lock.json). If an upstream tag changes and verification fails, review and update the pinned version instead of bypassing checks.

To verify existing assets without downloading or starting Ollama:

```powershell
.\.venv\Scripts\python.exe -I scripts\prepare_models.py --check
```

### 3. Start and use the application

Double-click **`start.cmd`**. The launcher opens `http://127.0.0.1:8080` and performs one-time local pairing. If navigating directly reports an unpaired session, reopen the launcher.

1. Import files and choose the detection method, output format and recovery option.
2. Review candidates on every page, add missed terms or rectangles, and confirm each page.
3. If recovery is enabled, set a password of at least 10 characters and export.
4. Download the redacted file, recovery bundle and report. Store the bundle and password separately.

Double-click **`stop.cmd`** to stop the services. Closing the browser alone does not stop the model server.

## Source layout

```text
backend/app/
  main.py          Local API, pairing, review, jobs and downloads
  engine.py        Parse → detect → review → export → verify
  detection.py     Rules, dictionaries, tokenizer and local extraction
  formats.py       Text parsing, format dispatch and content-review previews
  office.py        In-place OOXML redaction with styles and layout retained
  raster.py        OCR, PDF rendering, coordinates and pixel redaction
  storage.py       Encrypted artifacts and SQLite job storage
  vault.py         Password-encrypted bundles and exact recovery
  transport.py     Bounded in-memory multipart uploads
  worker.py        Single-job process and local-network restrictions
frontend/src/      React + TypeScript Chinese UI
scripts/           Source setup, model preparation, publication audit
backend/tests/     Unit, document, API and recovery tests
docs/assets/       Real UI screenshots and actual output illustrations
examples/          Public synthetic inputs and outputs
models.lock.json   Model digests and sources; no weights
```

See [architecture notes](docs/ARCHITECTURE.md) for the data flow, APIs and limitations.

## Testing and development

```powershell
.\.venv\Scripts\python.exe -I -m pytest -q
.\.venv\Scripts\python.exe -I scripts\audit_repository.py
```

After assets are prepared and the project's Ollama service is running:

```powershell
.\.venv\Scripts\python.exe -I -m pytest --run-integration -q
```

Default tests skip real-model/OCR integration cases. Font-dependent tests are skipped if the required font is absent. GitHub Actions includes backend checks without model downloads and a frontend build; consult the repository's actual workflow runs for CI status. After UI changes, run `npm run build` in `frontend` and restart the application. The production UI is served by the backend on the same port.

## Known limits

- 100 MiB per input file, at most 200 preview pages/images, 40 million pixels per image; 8 million bytes for TXT/CSV and 2 million extracted text characters.
- Native DOCX/XLSX preserves layout properties and font styles. Mask widths, missing fonts and reader differences can affect wrapping. Content previews and Office-to-PDF exports remain simplified. For fixed page appearance, export PDF from Office first, then redact that PDF.
- Excel conditional formatting and data validation are removed; static styles remain. Macros, comments, revision history and external links are not retained. PDF output retains visual appearance through image pages, without editable text.
- Recovery needs the unchanged corresponding output, bundle and password. Lost passwords cannot be recovered, and later edits are not merged.
- Inactive jobs are cleaned after their last update exceeds 24 hours. Downloads saved elsewhere remain under the user's control.
- Encryption, process isolation and the Python network guard are not an OS-level sandbox. See [SECURITY.md](SECURITY.md).

## Contributing and license

Improvements to parsers, rules, review UX and synthetic tests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md). Project code is under the [MIT License](LICENSE). Third-party models and dependencies retain their [upstream licenses](THIRD_PARTY_NOTICES.md).
