# PU Tool

本项目是一个本地运行的 Python CLI + Web 工具，用于本人账号查看 PU 口袋校园活动、展示活动类型和加分/学分/积分内容，并创建低频、有限重试的定时报名计划。

## 边界

- 仅用于用户本人的账号。
- 不保存明文密码。
- 不绕过验证码、风控、设备校验或平台访问控制。
- 不做暴力多线程、高并发抢报。
- 自动报名默认低频，默认只尝试 1 次，最多 3 次。
- 测试全部使用 mock fixture，不调用真实 PU 接口，不需要真实账号。

## 安装

```powershell
python -m pip install -e ".[dev]"
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
pu signup attempts
```

登录时必须提供学校 sid 或 class URL encoded sid；也可使用 `--sid 237791864815616`，或传入完整 class login URL。

活动列表和详情默认优先使用本地缓存，避免频繁刷新请求；需要实时数据时使用 `--refresh`。

`pu signup schedule` 只创建本地计划记录。计划执行依赖本地调度器，请保持 `pu serve` 运行；Web 服务启动时会恢复仍处于 `scheduled`、`retrying` 或 `running` 的 enabled 计划。
CLI `--at` 推荐显式带时区 offset；未带时区的时间会按运行机器的系统本地时区解释。

## Web

默认只绑定本机地址：

```powershell
pu serve --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000` 后可查看活动、详情、计划和尝试记录。页面会提示工具仅用于本人账号并遵守低频和风控边界。
Web 中活动列表/详情默认使用缓存，页面上的“强制刷新”按钮会显式请求最新数据。计划页和活动详情页均可创建计划，计划页可取消未完成计划。

## 后续移动端路线

当前版本不实现移动端 App，也不为移动端扩大首版范围。后续如果要做 Flutter、React Native 或 PWA，应复用现有分层：

- FastAPI 继续作为本地或自托管后端/API 层，保持稳定 JSON API。
- `service.py` 作为 CLI、Web、移动端共用的业务编排层，不把报名规则散落到 UI。
- `scheduler.py` 和 SQLite 计划/尝试记录继续负责低频定时报名、有限重试和审计记录。
- 移动端只做展示、登录触发、计划管理和状态查看，不新增高并发抢报、验证码绕过或风控绕过能力。
- 如果移动端需要远程访问后端，应另行设计认证、HTTPS、设备授权和数据保护；当前默认仍只绑定 `127.0.0.1`。

## 配置

可参考 `.env.example`。主要环境变量：

- `PU_BASE_URL`：默认 `https://apis.pocketuni.net`
- `PU_DB_PATH`：SQLite 数据库路径
- `PU_REQUEST_TIMEOUT_SECONDS`：默认 `10`
- `PU_MIN_REQUEST_INTERVAL_SECONDS`：默认 `2`
- `PU_MAX_RETRIES`：默认 `2`
- `PU_ACTIVITY_CACHE_TTL_SECONDS`：活动缓存 TTL，默认 `300`
- `PU_WEB_HOST`：默认 `127.0.0.1`
- `PU_WEB_PORT`：默认 `8000`

token 优先保存到 OS keyring。若 keyring 不可用，工具会显式使用本地 fallback 文件并给出风险提示；不会保存明文密码。

## 测试

```powershell
python -m pytest -v
python -m ruff check .
```

测试 fixture 均为合成数据，不含真实手机号、学号、token、sid 或个人信息。
