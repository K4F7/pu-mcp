# PU Tool

本项目是一个本地运行的 Python CLI，用于本人账号查看 PU 口袋校园活动、展示活动类型和加分/学分/积分内容，并管理待抢计划。网页已归档到 git 分支 `archive_frontend`。到点报名由外部调度（Hermes/OpenClaw）无模型调用 `pu signup run`。

## 边界

- 仅用于用户本人的账号。
- 不保存明文密码。
- 不绕过验证码、风控、设备校验或平台访问控制。
- 不做暴力多线程、高并发抢报。
- 自动报名默认低频，默认只尝试 1 次，最多 3 次。
- 测试全部使用 mock fixture，不调用真实 PU 接口，不需要真实账号。

## 安装

```powershell
uv sync --extra dev
```

## CLI 示例

```powershell
pu --help
pu login --username fake_user --encoded-sid QVpTRFBVS19QS1hRRVhS
pu auth status
pu activities list
pu activities list --refresh
pu activities info ACT-1001 --refresh
pu signup schedule ACT-1001 --at "2026-06-08T18:30:00+08:00"
pu signup plans
pu signup run 1
pu signup attempts
```

登录时必须提供学校 sid 或 class URL encoded sid；也可使用 `--sid 237791864815616`，或传入完整 class login URL。

活动列表和详情默认优先使用本地缓存，避免频繁刷新请求；需要实时数据时使用 `--refresh`。

`pu signup schedule` 只创建本地待抢记录。到点执行请调用 `pu signup run <plan_id>`（无模型一次报名），由 Hermes/OpenClaw 登记调度，不在本工具里跑常驻网页。
CLI `--at` 推荐显式带时区 offset；未带时区的时间会按运行机器的系统本地时区解释。

网页与 `pu serve` 在分支 `archive_frontend`。

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
uv run pytest -v
uv run ruff check .
```

测试 fixture 均为合成数据，不含真实手机号、学号、token、sid 或个人信息。
