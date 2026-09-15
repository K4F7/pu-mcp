from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from html import escape
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from pu_mcp.errors import (
    AuthError,
    BusinessError,
    NetworkError,
    ParseError,
    PuToolError,
    RateLimitError,
    RiskControlError,
)
from pu_mcp.pu_client import decode_school_sid
from pu_mcp.scheduler import LocalSignupScheduler
from pu_mcp.service import PuService, build_service
from pu_mcp.time_utils import ensure_aware_local


class LoginRequest(BaseModel):
    username: str
    password: str
    sid: str | None = None
    encoded_sid: str | None = None


class SignupPlanRequest(BaseModel):
    activity_id: str
    activity_title: str
    run_at: datetime
    max_attempts: int = 1

    @field_validator("run_at")
    @classmethod
    def normalize_run_at(cls, value: datetime) -> datetime:
        return ensure_aware_local(value)


def _html(title: str, active: str = "activities") -> str:
    safe_title = escape(title)
    safe_active = escape(active, quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body data-view="{safe_active}">
  <header class="topbar">
    <div>
      <strong>PU Tool</strong>
      <span>仅用于本人账号 · 低频请求 · 有限重试 · 不绕过验证码/风控</span>
    </div>
    <nav>
      <a href="/">活动</a>
      <a href="/plans">计划</a>
      <a href="/attempts">记录</a>
      <a href="/settings">设置</a>
    </nav>
  </header>
  <main>
    <section id="app-root" class="workspace"></section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>"""


def _exception_message(exc: Exception) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    return str(exc)


def _error_payload(code: str, message: str, retryable: bool) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "retryable": retryable}}


def _http_error_code(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 405:
        return "method_not_allowed"
    return "http_error"


def create_app(service: PuService | None = None, scheduler=None) -> FastAPI:
    singleton = service or build_service()
    scheduler_instance = scheduler
    if scheduler_instance is None and hasattr(singleton, "storage"):
        scheduler_instance = LocalSignupScheduler(singleton, singleton.storage)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if scheduler_instance is not None:
            scheduler_instance.start()
        try:
            yield
        finally:
            if scheduler_instance is not None:
                scheduler_instance.stop()

    app = FastAPI(title="PU Tool", version="0.1.0", lifespan=lifespan)
    static_path = Path(__file__).parent / "web_static"
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    def get_service() -> PuService:
        return singleton

    def json_error(status_code: int, code: str, exc: Exception, retryable: bool):
        return JSONResponse(
            status_code=status_code,
            content=_error_payload(code, _exception_message(exc), retryable),
        )

    @app.exception_handler(AuthError)
    def auth_error_handler(_request, exc: AuthError):
        return json_error(401, "auth_error", exc, False)

    @app.exception_handler(RiskControlError)
    def risk_error_handler(_request, exc: RiskControlError):
        return json_error(409, "risk_control_error", exc, False)

    @app.exception_handler(RateLimitError)
    def rate_limit_error_handler(_request, exc: RateLimitError):
        return json_error(429, "rate_limit_error", exc, True)

    @app.exception_handler(NetworkError)
    def network_error_handler(_request, exc: NetworkError):
        return json_error(503, "network_error", exc, True)

    @app.exception_handler(BusinessError)
    def business_error_handler(_request, exc: BusinessError):
        return json_error(422, "business_error", exc, False)

    @app.exception_handler(ParseError)
    def parse_error_handler(_request, exc: ParseError):
        return json_error(422, "parse_error", exc, False)

    @app.exception_handler(ValueError)
    def value_error_handler(_request, exc: ValueError):
        return json_error(400, "value_error", exc, False)

    @app.exception_handler(KeyError)
    def key_error_handler(_request, exc: KeyError):
        return json_error(404, "not_found", exc, False)

    @app.exception_handler(PuToolError)
    def pu_tool_error_handler(_request, exc: PuToolError):
        return json_error(400, "pu_tool_error", exc, False)

    @app.exception_handler(RequestValidationError)
    def request_validation_error_handler(_request, _exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                "validation_error",
                "request validation failed",
                False,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    def http_error_handler(_request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                _http_error_code(exc.status_code),
                str(exc.detail),
                False,
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _html("PU 活动", "activities")

    @app.get("/activities/{activity_id}", response_class=HTMLResponse)
    def activity_page(activity_id: str) -> str:
        return _html(f"活动 {activity_id}", f"activity:{activity_id}")

    @app.get("/plans", response_class=HTMLResponse)
    def plans_page() -> str:
        return _html("报名计划", "plans")

    @app.get("/attempts", response_class=HTMLResponse)
    def attempts_page() -> str:
        return _html("报名记录", "attempts")

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page() -> str:
        return _html("设置", "settings")

    @app.get("/api/auth/status")
    def auth_status(svc: PuService = Depends(get_service)):  # noqa: B008
        return svc.auth_status()

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest, svc: PuService = Depends(get_service)):  # noqa: B008
        if bool(payload.sid) == bool(payload.encoded_sid):
            raise ValueError("provide exactly one school sid: sid or encoded_sid")
        school_sid = payload.sid or decode_school_sid(payload.encoded_sid or "")
        session = await svc.login(payload.username, payload.password, school_sid)
        return {"authenticated": True, "user": session.masked_user}

    @app.post("/api/auth/logout")
    def logout(svc: PuService = Depends(get_service)):  # noqa: B008
        svc.logout()
        return {"ok": True}

    @app.get("/api/activities")
    async def activities(
        refresh: bool = False,
        svc: PuService = Depends(get_service),  # noqa: B008
    ):
        return [
            item.model_dump(mode="json")
            for item in await svc.list_activities(refresh=refresh)
        ]

    @app.get("/api/activities/joined")
    async def joined(svc: PuService = Depends(get_service)):  # noqa: B008
        return [item.model_dump(mode="json") for item in await svc.joined_activities()]

    @app.get("/api/activities/{activity_id}")
    async def activity_detail(
        activity_id: str,
        refresh: bool = False,
        svc: PuService = Depends(get_service),  # noqa: B008
    ):
        return (await svc.activity_detail(activity_id, refresh=refresh)).model_dump(mode="json")

    @app.post("/api/signup/plans")
    def create_plan(
        payload: SignupPlanRequest, svc: PuService = Depends(get_service)  # noqa: B008
    ):
        plan = svc.create_signup_plan(
            payload.activity_id,
            payload.activity_title,
            payload.run_at,
            payload.max_attempts,
        )
        if scheduler_instance is not None:
            scheduler_instance.register_plan(plan.plan_id or 0, plan.run_at)
        return plan.model_dump(mode="json")

    @app.get("/api/signup/plans")
    def plans(svc: PuService = Depends(get_service)):  # noqa: B008
        return [item.model_dump(mode="json") for item in svc.list_signup_plans()]

    @app.delete("/api/signup/plans/{plan_id}")
    def cancel_plan(plan_id: int, svc: PuService = Depends(get_service)):  # noqa: B008
        plan = svc.cancel_signup_plan(plan_id)
        if scheduler_instance is not None:
            scheduler_instance.cancel_plan(plan_id)
        return plan.model_dump(mode="json")

    @app.get("/api/signup/attempts")
    def attempts(
        plan_id: int | None = None, svc: PuService = Depends(get_service)  # noqa: B008
    ):
        return [item.model_dump(mode="json") for item in svc.list_signup_attempts(plan_id=plan_id)]

    return app
