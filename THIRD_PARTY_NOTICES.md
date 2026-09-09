# Third-party components / 第三方组件

The MIT license in this repository covers the project code. Models, inference engines and dependencies retain their own upstream licenses; the project license does not relicense those assets. Model weights and executable runtimes are not distributed in this repository.

本仓库的 MIT 许可适用于项目代码，不改变模型、推理引擎和依赖库各自的上游许可。仓库不分发模型权重或可执行运行环境。

| Component | Use | Upstream / license notice |
|---|---|---|
| Qwen3.5 | Local entity extraction | [Model card](https://huggingface.co/Qwen/Qwen3.5-9B) · [notice](licenses/Qwen-model-LICENSE.txt) |
| Ollama | Local inference server | [Upstream](https://github.com/ollama/ollama) · [notice](licenses/Ollama-LICENSE.txt) |
| PaddleOCR | OCR pipeline | [Upstream](https://github.com/PaddlePaddle/PaddleOCR) · [notice](licenses/PaddleOCR-LICENSE.txt) |
| PaddlePaddle | OCR inference runtime | [Upstream](https://github.com/PaddlePaddle/Paddle) · [notice](licenses/PaddlePaddle-LICENSE.txt) |
| React / React DOM / Scheduler | Browser UI | [React](licenses/react-LICENSE.txt) · [React DOM](licenses/react-dom-LICENSE.txt) · [Scheduler](licenses/scheduler-LICENSE.txt) |
| FastAPI, pypdf, PDFium, ReportLab, python-docx, openpyxl, cryptography and other Python packages | API, document handling and encryption | See each installed distribution's license and metadata; versions are locked in `backend/requirements-lock.txt`. |

Microsoft YaHei is a Windows system font used for preview rendering. The font is not included in this repository. Python, CUDA libraries and other downloaded distributions retain their vendor notices.
