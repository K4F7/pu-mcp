# Grok Bot Linux：AddMcpServer（stdio）

Grok Bot 的 AddMcpServer **没有 cwd / 不提供 cwd**，必须用 `uv --directory` 指向本仓库的绝对路径。command 用 `uv`，不要用 pu 当 command。

## 一次性准备

1. 安装 `uv`（install uv：https://docs.astral.sh/uv/getting-started/installation/），并确保 **Grok Bot 进程用到的 PATH** 里能找到 `uv`。AddMcpServer 的 command 是 `uv`；图形界面 / GUI 会话往往没有 `~/.local/bin`。若 GUI 找不到 `uv`，把 command 改成 `uv` 二进制的绝对路径（例如 `/home/you/.local/bin/uv`）。
2. 克隆本仓库（clone）。
3. 在仓库根执行：`uv sync --python 3.12 --extra dev`。
4. 把下面 `/path/to/pu-mcp` 换成仓库的真实绝对路径。
5. 登录只走 CLI；MCP 不收密码、不提供 login 工具。交互式本机登录一次（首选，不依赖全局 `pu`）：`uv run --python 3.12 --no-sync pu login --sid …`。仅当已激活 `.venv` 或 PATH 里已有 `pu` 时，才可用裸命令 `pu login --sid …`。无 TTY / Grok Bot 见下方非交互示例。
6. 把下面 command / args / env 贴进 AddMcpServer。不要填 cwd。AddMcpServer 的 env 是给 MCP 进程继承 HOME/PATH 用的，不要把 `PU_PASSWORD` 填进 MCP env。

## 非交互登录（Grok Bot / agent）

无 TTY 时不要依赖密码提示。一次传齐 `-u -p --sid`（占位符），或用环境变量。不要让用户把密码贴进对话。

优先 Grok Bot secret-request 或环境变量 `PU_USERNAME` / `PU_PASSWORD` / `PU_SID`（CLI typer envvar，对应 `-u` / `-p` / `--sid`），避免明文密码出现在 argv。三个都设好后可直接 `pu login`，省略 `-u -p --sid`。显式 `--sid` 覆盖 `PU_SID`。

```bash
uv run --python 3.12 --no-sync pu login
```

若 `PU_USERNAME` / `PU_PASSWORD` / `PU_SID` 已在环境中，可省略 `-u` / `-p` / `--sid`，直接 `pu login`。也可继续显式传 `-u -p --sid`。登录成功后用 `auth_status`（MCP）或 `pu auth status` 确认（脱敏）。

MCP 工具含 `join_activity` / `cancel_activity`：调用前须在对话里问用户确认；向 live PU 提交时使用数字 `activityId` 与 `X-Sign`（见 `src/pu_mcp/x_sign.py`）。

## Paste-ready：command / args / env（NO cwd）

```json
{
  "command": "uv",
  "args": ["--directory", "/path/to/pu-mcp", "run", "--python", "3.12", "--no-sync", "pu", "mcp"],
  "env": {}
}
```

- command = `"uv"`
- args = `["--directory", "/path/to/pu-mcp", "run", "--python", "3.12", "--no-sync", "pu", "mcp"]`
- env 可空。空 env 表示继承当前环境（不要清空 HOME/PATH）。AddMcpServer 不支持 cwd，因此 `--directory` 必填。

## 用户范围 TOML 等价（同样必须 `--directory`）

Grok Bot AddMcpServer 没有 cwd，user-scope 配置也必须用 `--directory`：

```toml
[mcp_servers.pu]
command = "uv"
args = ["--directory", "/path/to/pu-mcp", "run", "--python", "3.12", "--no-sync", "pu", "mcp"]
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

Grok Bot 没有 cwd，必须用上面的 `--directory /path/to/pu-mcp` 形式。

## Keyring fallback

token / session 优先写入 OS keyring。若 keyring 不可用，会落到本地文件：

- 路径：`~/.pu_mcp/session.json`（`Path.home() / ".pu_mcp" / "session.json"`）
- 旧路径 `~/.pu_tool/session.json` 在读取时会迁移到新路径
- POSIX 权限：`0600`（`0o600`）

本地文件安全性低于 OS keyring，请保护本机/用户账户；不要提交该文件。不保存密码（passwords never stored；只存 token/session）。
