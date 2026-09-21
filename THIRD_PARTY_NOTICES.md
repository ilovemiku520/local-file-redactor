# Third-party components / 第三方组件

Original project material is subject to the all-rights-reserved notice in LICENSE. Models, inference engines and dependencies retain their own upstream licenses; the project license does not relicense those assets. Model weights and executable runtimes are not distributed in this repository.

本仓库的原创内容适用 LICENSE 中的保留所有权利声明，不改变模型、推理引擎和依赖库各自的上游许可。仓库不分发模型权重或可执行运行环境。

| Component | Use | Upstream / license notice |
|---|---|---|
| Qwen3.5 | Local entity extraction | [Model card](https://huggingface.co/Qwen/Qwen3.5-9B) · [notice](licenses/Qwen-model-LICENSE.txt) |
| Ollama | Local inference server | [Upstream](https://github.com/ollama/ollama) · [notice](licenses/Ollama-LICENSE.txt) |
| PaddleOCR | OCR pipeline | [Upstream](https://github.com/PaddlePaddle/PaddleOCR) · [notice](licenses/PaddleOCR-LICENSE.txt) |
| PaddlePaddle | OCR inference runtime | [Upstream](https://github.com/PaddlePaddle/Paddle) · [notice](licenses/PaddlePaddle-LICENSE.txt) |
| React / React DOM / Scheduler | Browser UI | [React](licenses/react-LICENSE.txt) · [React DOM](licenses/react-dom-LICENSE.txt) · [Scheduler](licenses/scheduler-LICENSE.txt) |
| FastAPI, pypdf, PDFium, ReportLab, python-docx, openpyxl, cryptography and other Python packages | API, document handling and encryption | See each installed distribution's license and metadata; versions are locked in `backend/requirements-lock.txt`. |

Microsoft YaHei is a Windows system font used for preview rendering. The font is not included in this repository. Python, CUDA libraries and other downloaded distributions retain their vendor notices.
