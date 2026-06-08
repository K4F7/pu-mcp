# PU CLI + Web Tool Design

> 日期：2026-06-08  
> 状态：已确认方案，待实现  
> 范围：Python CLI + Web 工具，仅写设计，不包含源码实现

## 1. 目标

构建一个 Python 工具，用于本人账号拉取 PU 口袋校园活动，展示活动类型以及加分、学分、积分等内容，并支持对指定活动设置低频定时报名任务。

系统需要同时提供：

- CLI：适合本地快速登录、拉取活动、查看详情、创建/查看/取消定时报名任务。
- Web：适合浏览器中筛选活动、查看详情、管理计划任务。
- HTTP 客户端：封装 PU 接口访问、鉴权、错误处理和限频策略。
- 调度器：在本地进程内执行定时报名任务。
- 测试：用 mock HTTP 覆盖接口解析、调度逻辑、API 层和 CLI 行为，不调用真实 PU 接口。

## 2. 明确不做

- 不支持代替他人账号登录或批量账号池。
- 不绕过验证码、风控、设备校验、签名校验或其他访问控制。
- 不做暴力多线程抢报名。
- 不调用真实 PU 接口做自动化测试。
- 不保存明文密码。
- 不实现绕过学校、PU 平台或活动主办方规则的行为。
- 不保证报名成功；只按用户指定计划发起一次或有限次数尝试，并展示结果。

## 3. 合规与风控边界

实现必须遵守以下边界：

- **本人账号**：工具只面向用户本人的 PU 账号，UI 和 CLI 文案需要明确提示“仅用于本人账号”。
- **默认低频**：活动列表、详情、报名等请求需要有默认节流；同类操作不应短时间高频触发。
- **有限重试**：只允许对网络超时、临时 5xx 等可恢复错误做少量指数退避重试；登录失败、验证码、权限不足、风控提示、活动不可报名等业务失败不得重试轰炸。
- **不绕过风控**：如果接口提示验证码、登录异常、设备异常、风险校验等，系统应停止相关自动动作并提示用户手动处理。
- **不暴力并发**：调度器同一时间只执行有限数量任务，默认串行或小并发；同一活动报名任务需要互斥，避免重复提交。
- **审计可见**：所有报名尝试都记录时间、活动 ID、计划 ID、结果状态、错误摘要，便于用户自查。
- **本地优先**：默认使用本地 SQLite 和本机存储；不上传账号、token 或活动数据到第三方服务。
- **凭据保护**：token 存储应使用 OS keyring；如果 keyring 不可用，需显式提示风险后才允许落盘到配置文件，并且配置文件权限应尽量收紧。

## 4. 已知接口主线

参考基础域名：

- `https://apis.pocketuni.net`

参考接口：

- 登录：`POST /uc/user/login`
- 活动列表：`POST /apis/activity/list`
- 活动详情：`POST /apis/activity/info`
- 活动报名：`POST /apis/activity/join`
- 已报名列表：`POST /apis/activity/myList`

参考认证形式：

- `Authorization: Bearer <token>:<sid>`

说明：

- 以上接口来自前置探究和参考仓库，不应在测试中调用真实服务。
- 具体请求参数、响应字段和错误码应在实现阶段通过 mock fixture 固化为内部契约。
- 如果后续人工确认接口字段有变化，优先更新 schema、fixtures 和解析测试，再改实现。

## 5. 推荐技术栈

- Python 3.11 或 3.12。
- FastAPI：Web 后端和本地 HTTP API。
- Uvicorn：本地开发和运行服务。
- Typer：CLI 命令。
- httpx：异步 HTTP 客户端。
- Pydantic v2：配置、请求、响应、领域模型。
- APScheduler：本地定时报名任务；若项目倾向纯 asyncio，可用 asyncio 任务循环替代，但需保留持久化任务状态。
- SQLite：本地计划任务、活动缓存、报名结果记录。
- SQLAlchemy 2.x 或 SQLModel：持久化层。
- pytest：测试框架。
- respx：mock httpx 请求。
- pytest-asyncio 或 anyio：异步测试。
- ruff：lint 和格式化。

## 6. 总体架构

建议采用单仓库 Python package：

```text
pu_tool/
  pyproject.toml
  README.md
  src/pu_tool/
    __init__.py
    config.py
    models.py
    security.py
    pu_client.py
    activity_parser.py
    storage.py
    scheduler.py
    service.py
    cli.py
    web_app.py
    web_static/
  tests/
    fixtures/
```

模块边界：

- `config.py`：环境变量、配置文件路径、限频和重试默认值。
- `models.py`：活动、积分项、登录凭据、报名计划、报名结果等 Pydantic/ORM 模型。
- `security.py`：token 存取、敏感信息脱敏、keyring fallback。
- `pu_client.py`：所有 PU HTTP 请求；只暴露语义方法，不让 CLI/Web 直接拼接口。
- `activity_parser.py`：从接口响应中提取活动类型、加分、学分、积分等展示字段。
- `storage.py`：SQLite 初始化、任务持久化、活动缓存、报名记录。
- `scheduler.py`：计划任务注册、恢复、执行、互斥、有限重试。
- `service.py`：应用业务编排；CLI 和 Web 共用。
- `cli.py`：Typer CLI。
- `web_app.py`：FastAPI app、HTML 页面、JSON API。
- `web_static/`：简单前端资源；可先用 server-rendered HTML 或轻量原生 JS。

依赖方向：

```text
CLI/Web -> service -> pu_client/storage/scheduler/activity_parser/security
```

`pu_client` 不依赖 CLI 或 Web。`scheduler` 通过 `service` 或明确注入的报名函数执行任务，避免和 Web 层耦合。

## 7. 领域模型

核心对象建议如下：

- `AuthSession`
  - `token`
  - `sid`
  - `expires_at`，若接口无法提供过期时间则可为空
  - `masked_user`

- `Activity`
  - `activity_id`
  - `title`
  - `activity_type`
  - `start_time`
  - `end_time`
  - `signup_start_time`
  - `signup_end_time`
  - `location`
  - `organizer`
  - `status`
  - `credits`
  - `score_items`
  - `raw`

- `ScoreItem`
  - `kind`：`credit`、`academic_credit`、`point`、`unknown`
  - `label`
  - `value`
  - `unit`
  - `source_field`

- `SignupPlan`
  - `plan_id`
  - `activity_id`
  - `activity_title`
  - `run_at`
  - `enabled`
  - `status`：`scheduled`、`running`、`succeeded`、`failed`、`cancelled`
  - `max_attempts`
  - `attempt_count`
  - `created_at`
  - `updated_at`

- `SignupAttempt`
  - `attempt_id`
  - `plan_id`
  - `activity_id`
  - `attempted_at`
  - `status`
  - `response_code`
  - `message`
  - `risk_flag`

## 8. 功能设计

### 8.1 登录

CLI 和 Web 都通过同一 service 登录。

流程：

1. 用户输入账号密码。
2. `pu_client` 调用登录接口。
3. 登录成功后提取 `token` 和 `sid`。
4. `security` 保存 token；不保存明文密码。
5. 登录失败时显示脱敏错误；如果出现验证码、风险校验或异常登录提示，停止自动流程。

### 8.2 活动列表

CLI 提供类似以下能力：

- 查看最近活动。
- 按关键词筛选。
- 按活动类型筛选。
- 显示活动 ID、标题、类型、报名时间、活动时间、积分/学分摘要。

Web 提供：

- 活动列表页。
- 搜索框。
- 活动类型筛选。
- 活动状态筛选。
- 积分/学分类摘要列。
- 详情入口。

活动列表数据应允许缓存，避免刷新页面就频繁请求 PU。

### 8.3 活动详情与加分解析

详情页和 CLI 详情命令需要展示：

- 标题、组织方、地点、时间。
- 报名窗口和当前报名状态。
- 活动类型。
- 加分/学分/积分内容。
- 原始响应中无法归类的奖励字段，以“未识别奖励字段”方式展示，避免误导。

解析策略：

- 优先使用明确字段。
- 对参考仓库中出现过的字段名建立映射。
- 对未知字段保留 raw，并在测试 fixture 中补充样例后再扩展。
- 不用脆弱字符串猜测替代明确字段；如果必须根据文案解析，需标记来源和置信度。

### 8.4 定时报名

用户可以为某活动创建计划：

- 指定活动 ID。
- 指定执行时间。
- 指定最大尝试次数，默认 1，最大值需较小，例如 3。
- 指定重试间隔，默认指数退避，禁止密集循环。

执行规则：

- 到点前不会主动高频轮询报名状态。
- 到点后先检查本地是否已有成功记录。
- 可选检查已报名列表，避免重复报名。
- 执行报名接口。
- 如果成功，计划状态改为 `succeeded`。
- 如果业务失败，计划状态改为 `failed`，不盲目重试。
- 如果网络临时失败，按有限重试策略执行。
- 如果出现风控、验证码、认证失效，计划停止并标记 `risk_flag`。

### 8.5 已报名列表

用于：

- 展示用户已报名活动。
- 在执行定时报名前做去重确认。
- 帮助用户核验报名结果。

应避免频繁自动刷新，默认由用户主动触发或在计划执行前最多调用一次。

## 9. CLI 设计

建议命令：

```text
pu login
pu auth status
pu activities list
pu activities info <activity-id>
pu activities joined
pu signup schedule <activity-id> --at "2026-06-08 18:30:00"
pu signup plans
pu signup cancel <plan-id>
pu signup attempts [--plan-id <plan-id>]
pu serve --host 127.0.0.1 --port 8000
```

CLI 输出原则：

- 默认表格化，适合终端阅读。
- 提供 `--json` 便于脚本读取。
- 敏感字段永远脱敏。
- 风控或验证码提示需要明确终止自动动作。

## 10. Web 设计

建议本地 Web 功能：

- `/`：活动列表页。
- `/activities/{activity_id}`：活动详情页。
- `/plans`：报名计划管理页。
- `/attempts`：报名尝试记录页。
- `/settings`：登录状态和安全设置。

建议 JSON API：

- `GET /api/auth/status`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/activities`
- `GET /api/activities/{activity_id}`
- `GET /api/activities/joined`
- `POST /api/signup/plans`
- `GET /api/signup/plans`
- `DELETE /api/signup/plans/{plan_id}`
- `GET /api/signup/attempts`

Web 默认绑定 `127.0.0.1`，不要默认暴露到局域网。

前端形态可以先用 FastAPI 模板或静态 HTML + 原生 JS，不要求复杂 SPA。重点是清楚展示活动类型、积分/学分内容和计划状态。

## 11. 配置

推荐配置来源优先级：

1. CLI 参数。
2. 环境变量。
3. 用户配置文件。
4. 默认值。

配置项：

- `PU_BASE_URL`：默认 `https://apis.pocketuni.net`，测试中替换为 mock。
- `PU_DB_PATH`：SQLite 路径。
- `PU_REQUEST_TIMEOUT_SECONDS`：默认 10。
- `PU_MIN_REQUEST_INTERVAL_SECONDS`：默认 2 或更保守。
- `PU_MAX_RETRIES`：默认 2。
- `PU_WEB_HOST`：默认 `127.0.0.1`。
- `PU_WEB_PORT`：默认 `8000`。

## 12. 错误处理

错误分类：

- `AuthError`：登录失败、token 失效。
- `RiskControlError`：验证码、风控、异常登录。
- `RateLimitError`：请求过于频繁或被限流。
- `BusinessError`：活动不可报名、名额已满、重复报名、活动不存在。
- `NetworkError`：超时、连接失败。
- `ParseError`：响应字段缺失或结构不符合预期。

处理原则：

- 业务错误默认不重试。
- 风控错误停止自动流程。
- 网络错误可有限重试。
- 解析错误需要保留脱敏原始摘要，方便补 fixture。

## 13. 测试策略

所有测试必须使用 mock，不调用真实 PU 接口。

建议测试层次：

- 单元测试：
  - 活动列表响应解析。
  - 活动详情加分/学分/积分解析。
  - token 脱敏。
  - 风控错误识别。
  - 重试策略。

- 客户端测试：
  - 用 `respx` mock 登录、列表、详情、报名、已报名。
  - 验证 `Authorization: Bearer <token>:<sid>`。
  - 验证不会在业务失败时重复报名。

- 服务层测试：
  - 创建报名计划。
  - 执行到点任务。
  - 已成功报名时跳过重复报名。
  - 风控响应会停止计划。

- CLI 测试：
  - 用 Typer runner 验证命令输出。
  - 验证 `--json` 输出结构。

- Web 测试：
  - FastAPI TestClient 或 httpx ASGITransport。
  - 验证 API 状态码和响应结构。

## 14. 验收标准

实现完成后应满足：

- 可以通过 CLI 登录，并保存 token，不保存明文密码。
- 可以通过 CLI 拉取活动列表并展示活动类型和积分/学分摘要。
- 可以通过 CLI 查看活动详情并展示加分/学分/积分内容。
- 可以通过 CLI 创建、查看、取消定时报名计划。
- 可以启动本地 Web，在浏览器中查看活动、详情和计划。
- 定时任务到点后只对指定活动执行有限报名尝试，并记录结果。
- 风控、验证码、认证异常时停止自动操作并提示用户。
- 测试全部使用 mock，不依赖真实 PU 账号或真实接口。
- pytest、ruff 通过。

## 15. 参考资料

前置探究提到的参考仓库：

- `Ranch007/PU-SignUpBot-GUI`
- `DGYJ-fufu/nonebot-plugin-pu-activity`
- `MDGZSQLLC/PU-Auto-Message`
- `xiincs/pocketuni-helper`

这些仓库只作为接口和字段形态参考，不应直接复制实现。后续实现时如引用第三方代码，必须核查许可证并保留出处。
