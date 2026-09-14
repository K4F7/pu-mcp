# MCP 跑在本机，不托管

MCP 规范默认推远程 HTTP。本工具的 PU 会话在本机 keyring，活动缓存和待抢在本地库，使用者是本人。MCP 只给本机 agent 用（stdio）。不托管、不把会话送到远端。要发给没装 Python 的人再考虑 MCPB。
