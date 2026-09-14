from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp import Client

from pu_tool import mcp_server
from pu_tool.mcp_server import mcp
from pu_tool.pu_client import PuClient
from pu_tool.service import PuService
from pu_tool.storage import Storage

NANCHANG_SCHOOLS = [
    {
        "id": "237791864815616",
        "name": "南昌大学",
        "short": "ncu",
        "casUrl": "https://cas.example.edu.cn/ncu",
    },
    {
        "id": "111222333444555",
        "name": "南昌航空大学",
        "short": "nchu",
        "casUrl": "https://cas.example.edu.cn/nchu",
    },
]


class FakeService:
    async def search_schools(self, keyword, limit=20):
        if not str(keyword or "").strip():
            raise ValueError("keyword must not be empty")
        return NANCHANG_SCHOOLS


def _tool_payload(result) -> dict:
    if result.structured_content is not None:
        return result.structured_content
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    assert texts
    return json.loads(texts[0])


def _tool_error_text(result) -> str:
    return " ".join(block.text for block in result.content if getattr(block, "text", None))


@pytest.mark.asyncio
async def test_mcp_exposes_search_schools_without_login_tool():
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert "search_schools" in names
    assert "auth_status" in names
    assert "login" not in names
    assert "erke_status" not in names
    assert "list_activities" not in names
    assert "add_watch" not in names


@pytest.mark.asyncio
async def test_mcp_search_schools_returns_cli_shape(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_service", lambda: FakeService())
    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("search_schools", {"keyword": "南昌"})
    assert result.is_error is False
    assert _tool_payload(result) == {"schools": NANCHANG_SCHOOLS}


@pytest.mark.asyncio
async def test_mcp_search_schools_rejects_empty_keyword(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_service", lambda: FakeService())
    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("search_schools", {"keyword": "   "})
    assert result.is_error is True
    assert "keyword must not be empty" in _tool_error_text(result)


@pytest.mark.asyncio
async def test_mcp_initialize_handshake_lists_tools():
    async with Client(mcp, mode="legacy") as client:
        assert client.server_info is not None
        assert client.server_info.name == "pu"
        listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert "search_schools" in names
    assert "auth_status" in names
    assert "login" not in names


@pytest.mark.asyncio
@respx.mock
async def test_mcp_session_closes_http_client_after_search(fixture_json, tmp_path, monkeypatch):
    respx.get("https://mock.local/uc/school/list").mock(
        return_value=httpx.Response(200, json=fixture_json("school_list.json"))
    )

    class MemorySessionStore:
        def load(self):
            return None

        def save(self, session):
            return None

        def clear(self):
            return None

    pu_client = PuClient(base_url="https://mock.local", min_interval_seconds=0)
    service = PuService(
        client=pu_client,
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    mcp_server._service = None
    monkeypatch.setattr(mcp_server, "build_service", lambda: service)

    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("search_schools", {"keyword": "南昌"})
    assert result.is_error is False
    assert pu_client._client.is_closed is True
