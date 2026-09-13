from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pu_tool.errors import PuToolError, RiskControlError
from pu_tool.models import Activity
from pu_tool.pu_client import decode_school_sid
from pu_tool.service import build_service
from pu_tool.time_utils import ensure_aware_local

app = typer.Typer(help="PU 本地 CLI，仅用于本人账号。网页已归档到 archive_frontend。")
auth_app = typer.Typer(help="认证状态")
activities_app = typer.Typer(help="活动浏览")
signup_app = typer.Typer(help="待抢计划；到点由外部调度调用 run")

app.add_typer(auth_app, name="auth")
app.add_typer(activities_app, name="activities")
app.add_typer(signup_app, name="signup")

console = Console()


def _run(coro):
    return asyncio.run(coro)


def _score_summary(activity: Activity) -> str:
    return (
        " / ".join(f"{item.label}:{item.value}{item.unit}" for item in activity.score_items) or "-"
    )


def _print_error(exc: Exception) -> None:
    message = str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)
    if isinstance(exc, RiskControlError):
        console.print(f"[red]检测到验证码/风控提示，已停止自动操作：{message}[/red]")
    else:
        console.print(f"[red]{message}[/red]")


@app.callback()
def main() -> None:
    """仅用于本人账号；低频请求，有限重试，不绕过验证码或风控。"""


@app.command()
def login(
    username: Annotated[str, typer.Option("--username", "-u", prompt=True)],
    password: Annotated[str, typer.Option("--password", "-p", prompt=True, hide_input=True)],
    sid: Annotated[str | None, typer.Option("--sid")] = None,
    encoded_sid: Annotated[str | None, typer.Option("--encoded-sid")] = None,
) -> None:
    """登录并保存 session token；不会保存明文密码。"""
    if bool(sid) == bool(encoded_sid):
        console.print("[red]请提供且只提供一个学校 SID：--sid 或 --encoded-sid。[/red]")
        raise typer.Exit(1)
    school_sid = sid or decode_school_sid(encoded_sid or "")
    try:
        session = _run(build_service().login(username, password, school_sid))
    except (PuToolError, ValueError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(f"登录成功：{session.masked_user or username}，token 已安全保存。")


@auth_app.command("status")
def auth_status() -> None:
    """显示脱敏认证状态。"""
    status = build_service().auth_status()
    console.print(json.dumps(status, ensure_ascii=False, indent=2))


@activities_app.command("list")
def activities_list(
    keyword: Annotated[str | None, typer.Option("--keyword", "-k")] = None,
    activity_type: Annotated[str | None, typer.Option("--type")] = None,
    page: Annotated[int, typer.Option("--page", min=1)] = 1,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 20,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """列出活动，展示活动类型和加分/学分/积分摘要。"""
    try:
        activities = _run(
            build_service().list_activities(
                keyword=keyword,
                activity_type=activity_type,
                page=page,
                limit=limit,
                refresh=refresh,
            )
        )
    except PuToolError as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    if json_output:
        console.print(
            json.dumps(
                [item.model_dump(mode="json") for item in activities], ensure_ascii=False, indent=2
            )
        )
        return
    table = Table(title="PU 活动（仅用于本人账号）")
    table.add_column("活动 ID")
    table.add_column("标题")
    table.add_column("类型")
    table.add_column("报名时间")
    table.add_column("活动时间")
    table.add_column("加分/学分/积分")
    for item in activities:
        table.add_row(
            item.activity_id,
            item.title,
            item.activity_type,
            f"{item.signup_start_time or '-'} ~ {item.signup_end_time or '-'}",
            f"{item.start_time or '-'} ~ {item.end_time or '-'}",
            _score_summary(item),
        )
    console.print(table)


@activities_app.command("info")
def activities_info(
    activity_id: str,
    refresh: Annotated[bool, typer.Option("--refresh")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """查看活动详情。"""
    try:
        activity = _run(build_service().activity_detail(activity_id, refresh=refresh))
    except PuToolError as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    if json_output:
        console.print(json.dumps(activity.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return
    console.print(f"[bold]{activity.title}[/bold]")
    console.print(f"活动 ID：{activity.activity_id}")
    console.print(f"类型：{activity.activity_type}")
    console.print(f"组织方：{activity.organizer or '-'}")
    console.print(f"地点：{activity.location or '-'}")
    console.print(f"报名：{activity.signup_start_time or '-'} ~ {activity.signup_end_time or '-'}")
    console.print(f"活动：{activity.start_time or '-'} ~ {activity.end_time or '-'}")
    console.print(f"加分/学分/积分：{_score_summary(activity)}")


@activities_app.command("joined")
def joined_activities(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """查看已报名活动。"""
    try:
        activities = _run(build_service().joined_activities())
    except PuToolError as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    if json_output:
        console.print(
            json.dumps(
                [item.model_dump(mode="json") for item in activities], ensure_ascii=False, indent=2
            )
        )
        return
    for item in activities:
        console.print(
            f"{item.activity_id}\t{item.title}\t{item.activity_type}\t{_score_summary(item)}"
        )


@signup_app.command("schedule")
def signup_schedule(
    activity_id: str,
    at: Annotated[str, typer.Option("--at")],
    activity_title: Annotated[str, typer.Option("--title")] = "",
    max_attempts: Annotated[int, typer.Option("--max-attempts", min=1, max=3)] = 1,
) -> None:
    """创建低频定时报名计划。"""
    try:
        run_at = ensure_aware_local(datetime.fromisoformat(at.replace(" ", "T")))
        plan = build_service().create_signup_plan(
            activity_id,
            activity_title or activity_id,
            run_at,
            max_attempts=max_attempts,
        )
    except (ValueError, PuToolError, KeyError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2))
    console.print("计划已创建。到点抢请让 agent 在 Hermes/OpenClaw 登记无模型任务：")
    console.print(f"pu signup run {plan.plan_id}")


@signup_app.command("plans")
def signup_plans(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """查看报名计划。"""
    try:
        plans = build_service().list_signup_plans()
    except (ValueError, PuToolError, KeyError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    if json_output:
        console.print(
            json.dumps(
                [item.model_dump(mode="json") for item in plans], ensure_ascii=False, indent=2
            )
        )
        return
    table = Table(title="报名计划")
    table.add_column("ID")
    table.add_column("活动")
    table.add_column("执行时间")
    table.add_column("状态")
    table.add_column("尝试")
    for plan in plans:
        table.add_row(
            str(plan.plan_id),
            f"{plan.activity_id} {plan.activity_title}",
            str(plan.run_at),
            plan.status,
            f"{plan.attempt_count}/{plan.max_attempts}",
        )
    console.print(table)


@signup_app.command("cancel")
def signup_cancel(plan_id: int) -> None:
    """取消报名计划。"""
    try:
        plan = build_service().cancel_signup_plan(plan_id)
    except (ValueError, PuToolError, KeyError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2))


@signup_app.command("run")
def signup_run(plan_id: int) -> None:
    """无模型一次执行报名，给 Hermes/OpenClaw 调度调用。"""
    try:
        attempt = _run(build_service().execute_signup_plan(plan_id))
    except (ValueError, PuToolError, KeyError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False, indent=2))


@signup_app.command("attempts")
def signup_attempts(
    plan_id: Annotated[int | None, typer.Option("--plan-id")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """查看报名尝试记录。"""
    try:
        attempts = build_service().list_signup_attempts(plan_id=plan_id)
    except (ValueError, PuToolError, KeyError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    if json_output:
        console.print(
            json.dumps(
                [item.model_dump(mode="json") for item in attempts], ensure_ascii=False, indent=2
            )
        )
        return
    table = Table(title="报名尝试")
    table.add_column("ID")
    table.add_column("计划")
    table.add_column("活动")
    table.add_column("时间")
    table.add_column("状态")
    table.add_column("消息")
    for attempt in attempts:
        table.add_row(
            str(attempt.attempt_id),
            str(attempt.plan_id),
            attempt.activity_id,
            str(attempt.attempted_at),
            attempt.status,
            attempt.message,
        )
    console.print(table)


