# Grok Bot Linux：AddMcpServer（stdio）

Grok Bot 的 AddMcpServer **没有 cwd / 不提供 cwd**，必须用 `uv --directory` 指向本仓库的绝对路径。command 用 `uv`，不要用 pu 当 command。

## 一次性准备

1. 安装 `uv`（install uv：https://docs.astral.sh/uv/getting-started/installation/），并确保 **Grok Bot 进程用到的 PATH** 里能找到 `uv`。AddMcpServer 的 command 是 `uv`；图形界面 / GUI 会话往往没有 `~/.local/bin`。若 GUI 找不到 `uv`，把 command 改成 `uv` 二进制的绝对路径（例如 `/home/you/.local/bin/uv`）。
2. 克隆本仓库（clone）。
3. 在仓库根执行：`uv sync --python 3.12 --extra dev`。
4. 把下面 `/path/to/PU` 换成仓库的真实绝对路径。
5. 本机登录一次（首选，不依赖全局 `pu`）：`uv run --python 3.12 --no-sync pu login --sid …`。仅当已激活 `.venv` 或 PATH 里已有 `pu` 时，才可用裸命令 `pu login --sid …`。
6. 把下面 command / args / env 贴进 AddMcpServer。不要填 cwd。

## Paste-ready：command / args / env（NO cwd）

```json
{
  "command": "uv",
  "args": ["--directory", "/path/to/PU", "run", "--python", "3.12", "--no-sync", "pu", "mcp"],
  "env": {}
}
```

- command = `"uv"`
- args = `["--directory", "/path/to/PU", "run", "--python", "3.12", "--no-sync", "pu", "mcp"]`
- env 可空。空 env 表示继承当前环境（不要清空 HOME/PATH）。AddMcpServer 不支持 cwd，因此 `--directory` 必填。

## 用户范围 TOML 等价（同样必须 `--directory`）

Grok Bot AddMcpServer 没有 cwd，user-scope 配置也必须用 `--directory`：

```toml
[mcp_servers.pu]
command = "uv"
args = ["--directory", "/path/to/PU", "run", "--python", "3.12", "--no-sync", "pu", "mcp"]
startup_timeout_sec = 60
```

空 env 表示继承（不要清空 HOME/PATH）。Grok Bot AddMcpServer 没有 cwd，`--directory` 必填。

## 和 `.grok/config.toml` 的区别

本机从仓库根启动的 grok（cwd = repo root）用 `.grok/config.toml` 的相对路径形式，**不含 `--directory`**：

```toml
[mcp_servers.pu]
command = "uv"
args = ["run", "--python", "3.12", "--no-sync", "pu", "mcp"]
startup_timeout_sec = 60
```

Grok Bot 没有 cwd，必须用上面的 `--directory /path/to/PU` 形式。

## Keyring fallback

token / session 优先写入 OS keyring。若 keyring 不可用，会落到本地文件：

- 路径：`~/.pu_tool/session.json`（`Path.home() / ".pu_tool" / "session.json"`）
- POSIX 权限：`0600`（`0o600`）

本地文件安全性低于 OS keyring，请保护本机/用户账户；不要提交该文件。不保存密码（passwords never stored；只存 token/session）。
