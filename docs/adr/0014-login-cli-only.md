# 登录只走 CLI，MCP 不收账密

PU 登录是学校 sid + 账号 + 密码，换 token 进 keyring。本机 stdio 不需要 MCP OAuth。密码不进模型、不进 elicitation、不打开选学校页。`pu login` 收凭据；MCP 只读 `auth_status`，用已存会话调 PU。
