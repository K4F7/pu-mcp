# PU Tool

本项目是本地 CLI + stdio MCP，用本人 PU 账号访问口袋校园：查学校、列活动、详情、已报名、立即报名，并给出各活动类型已签到次数。登录只走 CLI；MCP 不收密码、不提供 login 工具。不保存待抢，不推荐场次，不代算有效学分。

仓库里残留的 Web / 调度代码不是本分支产品入口。

## 边界

- 仅用于用户本人的账号。
- 不保存明文密码。
- 不绕过验证码、风控、设备校验或平台访问控制。
- 不做暴力多线程、高并发抢报。
- 报名是当场向 PU 提交；没有 `pu signup` 产品入口。
- `pu erke` / MCP `attendance_counts` 只出已签到次数，不算有效学分。
- 测试全部使用 mock fixture，不调用真实 PU 接口，不需要真实账号。

## 安装

先安装 `uv`（install uv：https://docs.astral.sh/uv/getting-started/installation/），并确保 `uv` 在 `PATH` 中（图形界面会话可能没有 `~/.local/bin`）。用 `uv sync --python 3.12` / `uv run --python 3.12` 固定 Python 3.12（uv 会按需拉取 3.12）。推荐始终 `uv run --python 3.12 --no-sync pu …`，无需全局安装 `pu` 入口（不必把 `pu` 装到全局 PATH）。

```bash
uv sync --python 3.12 --extra dev
```

PowerShell 同样可执行上述命令。登录一次（把 sid 换成真实值）：

```bash
uv run --python 3.12 --no-sync pu login --sid …
```

## CLI

推荐始终 `uv run --python 3.12 --no-sync pu …`。若已激活 `.venv`（`source .venv/bin/activate`；Windows：`.venv\Scripts\Activate.ps1`），下面裸 `pu` 也可以。

```bash
uv run --python 3.12 --no-sync pu --help
uv run --python 3.12 --no-sync pu schools search 南昌 --json
uv run --python 3.12 --no-sync pu login --username fake_user --sid 237791864815616
uv run --python 3.12 --no-sync pu auth status
uv run --python 3.12 --no-sync pu activities list
uv run --python 3.12 --no-sync pu activities list --refresh
uv run --python 3.12 --no-sync pu activities info ACT-1001 --refresh
uv run --python 3.12 --no-sync pu activities joined
uv run --python 3.12 --no-sync pu activities join ACT-1001
uv run --python 3.12 --no-sync pu erke
uv run --python 3.12 --no-sync pu mcp
```

登录时必须提供学校 sid 或 class URL encoded sid；也可使用 `--encoded-sid`，或传入完整 class login URL。中文校名请先用 `uv run --python 3.12 --no-sync pu schools search` 查出数字 sid。

活动列表和详情默认优先使用本地缓存，避免频繁刷新请求；需要实时数据时使用 `--refresh`。`pu activities joined` 会标明每场是否已签到。`pu erke` 只打印各活动类型已签到次数。

## MCP

MCP 与 CLI 同一套能力（登录除外）。七个工具：

- `search_schools`
- `auth_status`
- `list_activities`
- `activity_detail`
- `list_joined`
- `attendance_counts`
- `join_activity`

登录只走 CLI：`uv run --python 3.12 --no-sync pu login --sid …`（已激活 `.venv` 时也可用裸 `pu login`）。调用 `join_activity` 前应在对话里问用户是否报名。进度只给已签到次数；认定规则在 glossary。

Grok 本机 stdio 启动（`--no-sync` 避免 `uv run` 文件锁挡住 initialize）：

```bash
uv run --python 3.12 --no-sync pu mcp
```

项目 `.grok/config.toml` 给 **cwd = 仓库根 / repo root** 的本机 grok 用，**不含 `--directory`**：

```toml
[mcp_servers.pu]
command = "uv"
args = ["run", "--python", "3.12", "--no-sync", "pu", "mcp"]
startup_timeout_sec = 60
```

Grok Bot（AddMcpServer，无 cwd）必须用 `--directory` 指向仓库绝对路径。粘贴参数见 [docs/agents/grok-bot-linux-mcp.md](docs/agents/grok-bot-linux-mcp.md)。

## 配置

可参考 `.env.example`。主要环境变量：

- `PU_BASE_URL`：默认 `https://apis.pocketuni.net`
- `PU_DB_PATH`：SQLite 数据库路径
- `PU_REQUEST_TIMEOUT_SECONDS`：默认 `10`
- `PU_MIN_REQUEST_INTERVAL_SECONDS`：默认 `2`
- `PU_MAX_RETRIES`：默认 `2`
- `PU_ACTIVITY_CACHE_TTL_SECONDS`：活动缓存 TTL，默认 `300`

token 优先保存到 OS keyring。若 keyring 不可用，会落到本地文件 `~/.pu_tool/session.json`（POSIX 权限 `0600`），并给出风险提示。本地文件安全性低于 OS keyring，请保护本机/用户账户；不要提交该文件。不保存密码（passwords never stored；只存 token/session）。

## 测试

```bash
uv run --python 3.12 pytest -v
uv run --python 3.12 ruff check .
```

测试 fixture 均为合成数据，不含真实手机号、学号、token、sid 或个人信息。
