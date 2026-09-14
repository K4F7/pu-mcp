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

```powershell
uv sync --python 3.12 --extra dev
```

## CLI

```powershell
pu --help
pu schools search 南昌 --json
pu login --username fake_user --sid 237791864815616
pu auth status
pu activities list
pu activities list --refresh
pu activities info ACT-1001 --refresh
pu activities joined
pu activities join ACT-1001
pu erke
pu mcp
```

登录时必须提供学校 sid 或 class URL encoded sid；也可使用 `--encoded-sid`，或传入完整 class login URL。中文校名请先用 `pu schools search` 查出数字 sid。

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

登录只走 CLI `pu login`。调用 `join_activity` 前应在对话里问用户是否报名。进度只给已签到次数；认定规则在 glossary。

Grok 本机 stdio 启动（`--no-sync` 避免 `uv run` 文件锁挡住 initialize）：

```powershell
uv run --python 3.12 --no-sync pu mcp
```

项目 `.grok/config.toml` 使用同一组参数：

```toml
[mcp_servers.pu]
command = "uv"
args = ["run", "--python", "3.12", "--no-sync", "pu", "mcp"]
startup_timeout_sec = 60
```

## 配置

可参考 `.env.example`。主要环境变量：

- `PU_BASE_URL`：默认 `https://apis.pocketuni.net`
- `PU_DB_PATH`：SQLite 数据库路径
- `PU_REQUEST_TIMEOUT_SECONDS`：默认 `10`
- `PU_MIN_REQUEST_INTERVAL_SECONDS`：默认 `2`
- `PU_MAX_RETRIES`：默认 `2`
- `PU_ACTIVITY_CACHE_TTL_SECONDS`：活动缓存 TTL，默认 `300`

token 优先保存到 OS keyring。若 keyring 不可用，工具会显式使用本地 fallback 文件并给出风险提示；不会保存明文密码。

## 测试

```powershell
uv run --python 3.12 pytest -v
uv run --python 3.12 ruff check .
```

测试 fixture 均为合成数据，不含真实手机号、学号、token、sid 或个人信息。
