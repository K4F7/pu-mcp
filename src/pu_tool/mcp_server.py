from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from pu_tool.service import PuService, build_service

INSTRUCTIONS = (
    "登录用本机 CLI `pu login --sid …`，这里不收密码、不提供 login 工具。"
    "未登录时可用 search_schools 按校名或简称查学校 sid，列出匹配项请用户确认后再登录。"
    "登录后用 auth_status 确认（脱敏）。"
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
    title="PU 学校查询",
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


def run_stdio() -> None:
    mcp.run(transport="stdio")
