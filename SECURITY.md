# Security / 安全说明

本项目处理敏感文件。请不要在公开 Issue、讨论、截图或日志中上传真实资料、密码、密钥或恢复包。报告问题时使用最小合成复现。如果仓库维护者已经启用 GitHub 私密漏洞报告，请优先使用仓库 Security 页面；否则先公开提交不含敏感细节的联系请求，等待维护者提供私密渠道。

默认仅监听本机回环地址。任务数据使用 AES-GCM 加密，密钥由当前 Windows 用户 DPAPI 保护；恢复包单独使用 Scrypt 与 AES-GCM。大文件上传在受限内存缓冲中接收。应用自动清理过期任务，下载到外部位置的文件由使用者自行保管。

文件解析在独立进程执行，并限制 Python 网络连接到本机；这不是操作系统级沙箱。同一 Windows 用户、管理员权限程序、进程内存及系统分页文件不在此隔离边界内。不要将服务改为公网监听，也不要把自动检测当成零遗漏保证。任何手工“保留原文”的选择都会影响成品。

Use minimal synthetic reproductions in public issues. Never post real documents, credentials, recovery bundles or private logs. If private vulnerability reporting is enabled for the repository, use its Security page; otherwise request a private contact without disclosing sensitive details publicly.

This is a single-user, loopback-only application. Encrypted job storage and isolated workers do not provide an OS-level sandbox against the same Windows account or an administrator. Automated detection requires human review. Do not expose the API to the public internet.
