from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pu_mcp.errors import PuToolError, RiskControlError
from pu_mcp.models import Activity
from pu_mcp.pu_client import decode_school_sid
from pu_mcp.service import build_service

app = typer.Typer(help="PU 本地 CLI + MCP 工具，仅用于本人账号。")
auth_app = typer.Typer(help="认证状态")
schools_app = typer.Typer(help="学校查询")
activities_app = typer.Typer(help="活动浏览")

app.add_typer(auth_app, name="auth")
app.add_typer(schools_app, name="schools")
app.add_typer(schools_app, name="school")
app.add_typer(activities_app, name="activities")

console = Console()


def _run(coro):
    return asyncio.run(coro)


def _cli_preview(value: str | None, *, limit: int = 24) -> str:
    if not value:
        return "-"
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


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
    ctx: typer.Context,
    username: Annotated[str, typer.Option("--username", "-u", prompt=True, envvar="PU_USERNAME")],
    password: Annotated[
        str,
        typer.Option("--password", "-p", prompt=True, hide_input=True, envvar="PU_PASSWORD"),
    ],
    sid: Annotated[str | None, typer.Option("--sid", envvar="PU_SID")] = None,
    encoded_sid: Annotated[str | None, typer.Option("--encoded-sid")] = None,
) -> None:
    """登录并保存 session token；不会保存明文密码。"""
    # Explicit --encoded-sid overrides inherited PU_SID (env), not a CLI --sid.
    # Compare by .name: typer may vendor a different ParameterSource enum than click.core.
    if (
        sid is not None
        and encoded_sid is not None
        and ctx.get_parameter_source("sid").name == "ENVIRONMENT"
    ):
        sid = None
    if bool(sid) == bool(encoded_sid):
        console.print("[red]请提供且只提供一个学校 SID：--sid 或 --encoded-sid。[/red]")
        raise typer.Exit(1)
    if sid is not None and not sid.isdigit():
        console.print("[red]学校 SID 必须是数字；请先用 `pu schools search` 按校名查询。[/red]")
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


@schools_app.command("search")
def school_search(
    keyword: str,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 20,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """按校名或简称查询学校 sid。未登录可调。"""
    try:
        schools = _run(build_service().search_schools(keyword, limit=limit))
    except (PuToolError, ValueError) as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    payload = {"schools": schools}
    if json_output:
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    table = Table(title="学校查询")
    table.add_column("sid")
    table.add_column("名称")
    table.add_column("简称")
    for item in schools:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("name") or ""),
            str(item.get("short") or ""),
        )
    console.print(table)


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
    # Human table keeps agent-readable fields; times/scores remain in --json / info.
    table = Table(title="PU 活动（仅用于本人账号）", padding=(0, 0))
    table.add_column("活动 ID", no_wrap=True)
    table.add_column("标题", overflow="ellipsis", max_width=10)
    table.add_column("类型", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("报名状态", no_wrap=True)
    table.add_column("可报", no_wrap=True)
    table.add_column("地点", overflow="ellipsis", max_width=12)
    table.add_column("内容", overflow="ellipsis", max_width=10)
    for item in activities:
        table.add_row(
            item.activity_id,
            item.title,
            item.activity_type,
            item.status or "-",
            item.signup_status or "-",
            "是" if item.allow_signup else "否",
            item.location or "-",
            _cli_preview(item.content, limit=18),
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
    console.print(f"内容：{activity.content or '-'}")
    console.print(f"状态：{activity.status or '-'}")
    console.print(f"报名状态：{activity.signup_status or '-'}")
    console.print(f"可报：{'是' if activity.allow_signup else '否'}")
    capacity = "-" if activity.capacity is None else str(activity.capacity)
    joined = "-" if activity.joined_count is None else str(activity.joined_count)
    full = "是" if activity.is_full else "否"
    console.print(f"名额：{joined}/{capacity}（满员：{full}）")
    console.print(f"报名：{activity.signup_start_time or '-'} ~ {activity.signup_end_time or '-'}")
    console.print(f"活动：{activity.start_time or '-'} ~ {activity.end_time or '-'}")
    console.print(f"加分/学分/积分：{_score_summary(activity)}")


@activities_app.command("joined")
def joined_activities(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """查看已报名活动，标明是否已签到。"""
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
    table = Table(title="已报名活动", padding=(0, 0))
    table.add_column("活动 ID", no_wrap=True)
    table.add_column("标题", overflow="ellipsis", max_width=8)
    table.add_column("类型", no_wrap=True)
    table.add_column("状态", no_wrap=True)
    table.add_column("报名状态", no_wrap=True)
    table.add_column("可报", no_wrap=True)
    table.add_column("地点", overflow="ellipsis", max_width=10)
    table.add_column("内容", overflow="ellipsis", max_width=8)
    table.add_column("签到", no_wrap=True)
    for item in activities:
        table.add_row(
            item.activity_id,
            item.title,
            item.activity_type,
            item.status or "-",
            item.signup_status or "-",
            "是" if item.allow_signup else "否",
            item.location or "-",
            _cli_preview(item.content, limit=14),
            "已签到" if item.signed_in else "未签到",
        )
    console.print(table)


@activities_app.command("join")
def activities_join(activity_id: str) -> None:
    """立即向 PU 提交报名。"""
    try:
        result = _run(build_service().join_activity(activity_id))
    except PuToolError as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@activities_app.command("cancel")
def activities_cancel(activity_id: str) -> None:
    """立即向 PU 取消报名。"""
    try:
        result = _run(build_service().cancel_activity(activity_id))
    except PuToolError as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("erke")
def erke() -> None:
    """打印各活动类型已签到次数，与 MCP attendance_counts 同一结构。"""
    try:
        counts = _run(build_service().attendance_counts())
    except PuToolError as exc:
        _print_error(exc)
        raise typer.Exit(1) from exc
    console.print(json.dumps({"counts": counts}, ensure_ascii=False, indent=2))


@app.command("mcp")
def mcp_stdio() -> None:
    """以 stdio 启动 MCP，供 agent 访问本人 PU 账号。"""
    from pu_mcp.mcp_server import run_stdio

    run_stdio()
