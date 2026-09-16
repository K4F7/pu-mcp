from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from pu_mcp.errors import PuToolError
from pu_mcp.models import Activity
from pu_mcp.service import PuService, build_service

INSTRUCTIONS = (
    "登录用本机 CLI `pu login --sid …`，这里不收密码、不提供 login 工具。"
    "未登录时可用 search_schools 按校名或简称查学校 sid，列出匹配项请用户确认后再登录。"
    "登录后用 auth_status 确认（脱敏）。"
    "调用 join_activity 报名前，先在对话里问用户是否报名。"
    "调用 cancel_activity 取消报名前，先在对话里问用户是否取消。"
    "进度只给出已签到次数；认定规则以 glossary 为准，本工具不代算有效学分。"
)

_service: PuService | None = None


async def _aclose_cached_service() -> None:
    global _service
    service = _service
    _service = None
    if service is None:
        return
    client = getattr(service, "client", None)
    aclose = getattr(client, "aclose", None)
    if aclose is None:
        return
    await aclose()


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await _aclose_cached_service()


mcp = MCPServer(
    "pu",
    title="PU 本人账号访问",
    instructions=INSTRUCTIONS,
    version="0.1.0",
    lifespan=_lifespan,
)


def get_service() -> PuService:
    global _service
    if _service is None:
        _service = build_service()
    return _service


@mcp.tool()
async def search_schools(keyword: str, limit: int = 20) -> dict:
    """按校名或简称查询学校 sid。未登录可调。

    默认最多返回 20 条；多条结果时列出匹配项（不超过 limit），请用户确认后再登录。
    """
    try:
        schools = await get_service().search_schools(keyword, limit=limit)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return {"schools": schools}


@mcp.tool()
async def auth_status() -> dict:
    """查看是否已登录（脱敏）。未登录时请用户在本机运行 pu login --sid …。"""
    return get_service().auth_status()


def _activity_payload(activity: Activity) -> dict:
    return activity.model_dump(mode="json", exclude={"raw"})


@mcp.tool()
async def list_activities(
    keyword: str | None = None,
    activity_type: str | None = None,
    page: int = 1,
    limit: int = 20,
    refresh: bool = False,
) -> dict:
    """列出活动。不按缺口筛选，不代替挑选活动。"""
    try:
        filters: dict[str, object] = {"page": page, "limit": limit, "refresh": refresh}
        if keyword:
            filters["keyword"] = keyword
        if activity_type:
            filters["activity_type"] = activity_type
        activities = await get_service().list_activities(**filters)
    except PuToolError as exc:
        raise ToolError(str(exc)) from exc
    return {"activities": [_activity_payload(item) for item in activities]}


@mcp.tool()
async def activity_detail(activity_id: str, refresh: bool = False) -> dict:
    """查看单个活动详情。"""
    try:
        activity = await get_service().activity_detail(activity_id, refresh=refresh)
    except PuToolError as exc:
        raise ToolError(str(exc)) from exc
    return _activity_payload(activity)


@mcp.tool()
async def list_joined() -> dict:
    """列出已报名活动，含 signed_in。"""
    try:
        activities = await get_service().joined_activities()
    except PuToolError as exc:
        raise ToolError(str(exc)) from exc
    return {"activities": [_activity_payload(item) for item in activities]}


@mcp.tool()
async def attendance_counts() -> dict:
    """各活动类型已签到次数。报名未签到不计。计入社会实践、校园文化、思想引领、学科竞赛、学术讲座、体育健身；志愿服务、创新创业不计。"""
    try:
        counts = await get_service().attendance_counts()
    except PuToolError as exc:
        raise ToolError(str(exc)) from exc
    return {"counts": counts}


@mcp.tool()
async def join_activity(activity_id: str) -> dict:
    """立即向 PU 提交报名。activityId 须为数字；请求带 X-Sign（见 pu_mcp.x_sign）。

    已报名等业务错误原样返回。调用前先在对话里问用户。
    """
    try:
        return await get_service().join_activity(activity_id)
    except PuToolError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def cancel_activity(activity_id: str) -> dict:
    """立即向 PU 取消报名。activityId 须为数字；请求带 X-Sign（见 pu_mcp.x_sign）。

    已取消、不可取消等业务错误原样返回。调用前先在对话里问用户。
    """
    try:
        return await get_service().cancel_activity(activity_id)
    except PuToolError as exc:
        raise ToolError(str(exc)) from exc


def run_stdio() -> None:
    mcp.run(transport="stdio")
