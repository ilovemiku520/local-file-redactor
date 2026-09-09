# GitHub 发布说明

项目仓库：[ilovemiku520/local-file-redactor](https://github.com/ilovemiku520/local-file-redactor)。公开仓库，默认分支 `main`，代码使用根目录 MIT 许可。中英文 README 已互相链接，GitHub 默认显示中文版本。以下说明供维护者发布更新或其他使用者发布自己的副本时参考。

## 中文 About 简介

本地文件脱敏与加密恢复工具：基于 Qwen3.5、PaddleOCR 和规则识别，支持 Word、Excel、PDF、文本、CSV、图片的逐页复核与多格式导出。文件在本机处理，模型权重单独下载。

## 建议 Topics

`document-redaction`, `pii-detection`, `privacy`, `local-llm`, `ollama`, `qwen`, `paddleocr`, `ocr`, `fastapi`, `react`, `chinese`, `windows`

## 发布内容

上传本项目根目录中的源码、README、docs、examples、licenses、scripts 和 `.github` 配置。不要上传外层已有部署项目、完整离线包、`runtime/`、`.venv/`、`work/`、真实用户文件或恢复包。发布前运行：

```powershell
.\.venv\Scripts\python.exe -I scripts\audit_repository.py
git status --short
```

若要发布自己的副本，先在你自己的 GitHub 账号/组织中建立空仓库，不要另勾选生成 README。若从 ZIP 解压，先在解压后的项目根目录执行 `git init -b main`。若只是参与现有项目，请优先 Fork 并提交 Pull Request。

首次使用 Git 时，设置你希望公开显示的提交者姓名和邮箱；邮箱可使用 GitHub 个人设置中提供的隐私邮箱。下面均为待替换占位值，不要原样执行：

```powershell
git config user.name "YOUR_NAME"
git config user.email "YOUR_GITHUB_EMAIL"
```

使用你实际的仓库地址完成首次提交和推送：

```powershell
git add .
git commit -m "Initial open-source release"
git remote add origin https://github.com/YOUR_ACCOUNT/local-file-redactor.git
git push -u origin main
```

也可以使用 GitHub Desktop 的“Add existing repository”选择本目录，然后“Publish repository”。不要添加整个上层部署目录。

GitHub Actions 会在推送后运行基础检查和前端构建；真实模型/OCR 集成测试需在准备好权重的 Windows 本机运行。GitHub About 简介与 Topics 需要在仓库页面设置，内容也已保存在 [repository.json](../.github/repository.json)。

截图使用相对路径，不依赖本地盘符或外部图床；源码包不包含模型权重。若修改截图或示例，应继续使用明确标注的合成资料。
