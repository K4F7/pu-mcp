from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp import Client

from pu_tool import mcp_server
from pu_tool.errors import BusinessError
from pu_tool.mcp_server import mcp
from pu_tool.models import Activity
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


JOINED_ACTIVITIES = [
    Activity(
        activity_id="ACT-2001",
        title="已签到合成活动",
        activity_type="校园文化",
        signed_in=True,
        raw={"internal": True},
    ),
    Activity(
        activity_id="ACT-2002",
        title="未签到合成活动",
        activity_type="社会实践",
        signed_in=False,
    ),
]
ATTENDANCE_COUNTS = {
    "社会实践": 0,
    "校园文化": 1,
    "思想引领": 0,
    "学科竞赛": 0,
    "学术讲座": 0,
    "体育健身": 0,
}


class FakeService:
    async def search_schools(self, keyword, limit=20):
        if not str(keyword or "").strip():
            raise ValueError("keyword must not be empty")
        return NANCHANG_SCHOOLS

    async def list_activities(
        self, keyword=None, activity_type=None, page=1, limit=20, refresh=False
    ):
        self.list_filters = {
            "keyword": keyword,
            "activity_type": activity_type,
            "page": page,
            "limit": limit,
            "refresh": refresh,
        }
        return JOINED_ACTIVITIES

    async def activity_detail(self, activity_id, refresh=False):
        return JOINED_ACTIVITIES[0]

    async def joined_activities(self):
        return JOINED_ACTIVITIES

    async def attendance_counts(self):
        return ATTENDANCE_COUNTS

    async def join_activity(self, activity_id):
        self.joined_id = activity_id
        return {"code": 0, "msg": "报名成功"}

    def auth_status(self):
        return {"authenticated": True, "token": "t...en", "sid": "s...id"}


def _tool_payload(result) -> dict:
    if result.structured_content is not None:
        return result.structured_content
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    assert texts
    return json.loads(texts[0])


def _tool_error_text(result) -> str:
    return " ".join(block.text for block in result.content if getattr(block, "text", None))


EXPECTED_MCP_TOOLS = {
    "auth_status",
    "search_schools",
    "list_activities",
    "activity_detail",
    "list_joined",
    "attendance_counts",
    "join_activity",
}
FORBIDDEN_MCP_TOOLS = {
    "login",
    "erke_status",
    "add_watch",
    "list_watch",
    "cancel_watch",
}


@pytest.mark.asyncio
async def test_mcp_exposes_search_schools_without_login_tool():
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert names == EXPECTED_MCP_TOOLS
    assert names.isdisjoint(FORBIDDEN_MCP_TOOLS)
    list_tool = next(tool for tool in tools if tool.name == "list_activities")
    schema = list_tool.input_schema or {}
    properties = schema.get("properties") or {}
    assert "fillable_only" not in properties
    assert {"keyword", "activity_type", "page", "limit", "refresh"} <= set(properties)


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
async def test_mcp_attendance_counts_returns_service_results(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_service", lambda: FakeService())
    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("attendance_counts", {})
    assert result.is_error is False
    payload = _tool_payload(result)
    assert payload == {"counts": ATTENDANCE_COUNTS}
    blob = str(payload)
    assert "必须补" not in blob
    assert "已获" not in blob
    assert "总有效分" not in blob
    assert "阶段线" not in blob
    assert "recommended_types" not in blob


@pytest.mark.asyncio
async def test_mcp_join_activity_returns_service_result(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(mcp_server, "get_service", lambda: service)
    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("join_activity", {"activity_id": "ACT-1001"})
    assert result.is_error is False
    assert service.joined_id == "ACT-1001"
    assert _tool_payload(result) == {"code": 0, "msg": "报名成功"}


@pytest.mark.asyncio
async def test_mcp_join_activity_returns_business_error(monkeypatch):
    class FailingService(FakeService):
        async def join_activity(self, activity_id):
            raise BusinessError("已报名该活动")

    monkeypatch.setattr(mcp_server, "get_service", lambda: FailingService())
    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("join_activity", {"activity_id": "ACT-1001"})
    assert result.is_error is True
    assert "已报名该活动" in _tool_error_text(result)


@pytest.mark.asyncio
async def test_mcp_list_joined_includes_signed_in_without_raw(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_service", lambda: FakeService())
    async with Client(mcp, mode="legacy") as client:
        result = await client.call_tool("list_joined", {})
    assert result.is_error is False
    payload = _tool_payload(result)
    assert "activities" in payload
    assert payload["activities"][0]["activity_id"] == "ACT-2001"
    assert payload["activities"][0]["signed_in"] is True
    assert payload["activities"][1]["signed_in"] is False
    assert "raw" not in payload["activities"][0]
    assert "internal" not in str(payload)


@pytest.mark.asyncio
async def test_mcp_initialize_handshake_lists_tools():
    async with Client(mcp, mode="legacy") as client:
        assert client.server_info is not None
        assert client.server_info.name == "pu"
        listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert names == EXPECTED_MCP_TOOLS
    assert names.isdisjoint(FORBIDDEN_MCP_TOOLS)


@pytest.mark.asyncio
async def test_mcp_instructions_ask_before_join_login_cli_and_counts():
    async with Client(mcp, mode="legacy") as client:
        instructions = client.instructions or ""
        listed = await client.list_tools()
    assert "pu login" in instructions
    assert "问用户" in instructions
    assert "报名" in instructions
    assert "已签到次数" in instructions
    assert "不代算有效学分" in instructions
    assert "glossary" in instructions
    descriptions = " ".join(tool.description or "" for tool in listed.tools)
    combined = instructions + " " + descriptions
    assert "0.1" not in combined
    assert "必须补" not in combined
    assert "阶段线" not in combined
    assert "总有效分" not in combined
    assert "已获" not in combined
    assert "志愿公益" not in combined
    assert "学分缺口" not in combined
    list_tool = next(tool for tool in listed.tools if tool.name == "list_activities")
    counts_tool = next(tool for tool in listed.tools if tool.name == "attendance_counts")
    list_desc = list_tool.description or ""
    counts_desc = counts_tool.description or ""
    assert "不按缺口筛选" in list_desc
    assert "不代替挑选活动" in list_desc
    assert "学分缺口" not in list_desc
    assert "志愿公益" not in counts_desc
    assert "志愿服务" in counts_desc
    assert "创新创业" in counts_desc
    for activity_type in (
        "社会实践",
        "校园文化",
        "思想引领",
        "学科竞赛",
        "学术讲座",
        "体育健身",
    ):
        assert activity_type in counts_desc


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
