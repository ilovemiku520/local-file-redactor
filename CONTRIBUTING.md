# 贡献指南 / Contributing

[中文说明](README.md) · [English overview](README.en.md)

参与开发前须事先取得书面许可，详见 [LICENSE](LICENSE)；Star 不构成授权。取得授权后，可改进文件解析、识别规则、人工复核体验和测试覆盖。提交问题或 PR 时请使用合成资料，不要上传真实合同、证件、恢复包、密码、工作文件或日志中的个人信息。

1. 按 README 配置 Python 3.12 与 Node.js 22。
2. 运行 `python -m pytest -q`。需要模型的检查必须在准备权重后加 `--run-integration`。
3. 在 `frontend` 中运行 `npm ci`、`npm run build`。
4. 运行 `python scripts/audit_repository.py`，检查模型、私人数据及失效文档链接。
5. PR 中说明问题、可复现的合成输入、修改后的行为及测试结果。仅在有新的证据时更新准确率或性能结论。

提交模型版本更新时，应同时审阅上游来源、许可、模板及权重摘要，并更新 `models.lock.json`；不要只修改模型名称。不要提交 `runtime/`、`.venv/`、`work/`、真实文件或 `.rdvault`。

Prior written permission is required before development; see [LICENSE](LICENSE). A GitHub Star does not grant permission. Authorized contributions to parsers, detection rules, review UX and regression coverage are welcome. Use synthetic fixtures only. Explain the trigger, resulting behavior and relevant validation in each PR. Run backend tests, build the frontend, and run the publication audit before submitting. Integration checks require separately downloaded assets. Changes to model versions must include a reviewed source, license, template and digest update; never commit weights or private files.

Contribution rights and any permission to incorporate or redistribute contributions must be agreed separately in writing with the applicable rights holder. Submission alone does not grant an MIT license or transfer copyright.
