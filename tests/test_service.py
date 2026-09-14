from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pu_tool.models import AuthSession
from pu_tool.service import PuService
from pu_tool.storage import Storage


class MemorySessionStore:
    def __init__(self):
        self.session = None

    def save(self, session):
        self.session = session

    def load(self):
        return self.session

    def clear(self):
        self.session = None


class FakeClient:
    def __init__(self, fixture_json):
        self.fixture_json = fixture_json
        self.join_calls = 0
        self.activity_list_calls = 0
        self.activity_list_filters = []
        self.activity_info_calls = 0

    async def login(self, username, password, school_sid):
        self.login_call = {
            "username": username,
            "password": password,
            "school_sid": school_sid,
        }
        return AuthSession(
            token="test-token-abcdef123456", sid="test-sid-654321", masked_user=username
        )

    async def activity_list(self, **filters):
        self.activity_list_calls += 1
        self.activity_list_filters.append(filters)
        return self.fixture_json("activity_list.json")

    async def activity_info(self, activity_id):
        self.activity_info_calls += 1
        return self.fixture_json("activity_info_credit.json")

    async def my_list(self):
        return self.fixture_json("my_list_joined.json")

    async def join_activity(self, activity_id):
        self.join_calls += 1
        return {"code": 0, "msg": "报名成功"}

    async def school_list(self):
        return self.fixture_json("school_list.json")["data"]["list"]


@pytest.mark.asyncio
async def test_service_login_stores_session_and_masks_status(tmp_path):
    store = MemorySessionStore()
    client = FakeClient(lambda _: {})
    service = PuService(
        client=client,
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=store,
    )
    await service.login("demo_user", "secret", school_sid="237791864815616")
    status = service.auth_status()
    assert status["authenticated"] is True
    assert "abcdef123456" not in status["token"]
    assert client.login_call == {
        "username": "demo_user",
        "password": "secret",
        "school_sid": "237791864815616",
    }


@pytest.mark.asyncio
async def test_service_login_stores_auth_sid_from_response_not_school_sid(tmp_path):
    store = MemorySessionStore()
    client = FakeClient(lambda _: {})
    service = PuService(
        client=client,
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=store,
    )

    session = await service.login("demo_user", "secret", school_sid="237791864815616")

    assert session.sid == "test-sid-654321"
    assert store.load().sid == "test-sid-654321"
    assert store.load().sid != "237791864815616"


@pytest.mark.asyncio
async def test_search_schools_rejects_empty_keyword(fixture_json, tmp_path):
    service = PuService(
        client=FakeClient(fixture_json),
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    with pytest.raises(ValueError, match="empty"):
        await service.search_schools("")


@pytest.mark.asyncio
async def test_search_schools_nanchang_returns_multi_hit_list(fixture_json, tmp_path):
    service = PuService(
        client=FakeClient(fixture_json),
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    schools = await service.search_schools("南昌")
    assert schools == [
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


@pytest.mark.asyncio
async def test_search_schools_matches_pinyin_short(fixture_json, tmp_path):
    service = PuService(
        client=FakeClient(fixture_json),
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    schools = await service.search_schools("ncu")
    assert schools == [
        {
            "id": "237791864815616",
            "name": "南昌大学",
            "short": "ncu",
            "casUrl": "https://cas.example.edu.cn/ncu",
        }
    ]


@pytest.mark.asyncio
async def test_search_schools_rejects_whitespace_keyword(fixture_json, tmp_path):
    service = PuService(
        client=FakeClient(fixture_json),
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    with pytest.raises(ValueError, match="empty"):
        await service.search_schools("   ")


@pytest.mark.asyncio
async def test_search_schools_limit_caps_results(fixture_json, tmp_path):
    service = PuService(
        client=FakeClient(fixture_json),
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    schools = await service.search_schools("南昌", limit=1)
    assert schools == [
        {
            "id": "237791864815616",
            "name": "南昌大学",
            "short": "ncu",
            "casUrl": "https://cas.example.edu.cn/ncu",
        }
    ]


@pytest.mark.asyncio
async def test_service_lists_and_details_activities(fixture_json, tmp_path):
    service = PuService(
        client=FakeClient(fixture_json),
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )
    activities = await service.list_activities()
    detail = await service.activity_detail("ACT-1001")
    assert activities[0].activity_type == "志愿公益"
    assert detail.activity_id == "ACT-1001"


@pytest.mark.asyncio
async def test_service_activity_list_defaults_to_page_and_limit(fixture_json, tmp_path):
    client = FakeClient(fixture_json)
    service = PuService(
        client=client,
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )

    await service.list_activities()

    assert client.activity_list_filters == [{"page": 1, "limit": 20}]


@pytest.mark.asyncio
async def test_service_uses_activity_cache_until_refresh_requested(fixture_json, tmp_path):
    client = FakeClient(fixture_json)
    service = PuService(
        client=client, storage=Storage(tmp_path / "pu.sqlite"), session_store=MemorySessionStore()
    )

    first = await service.list_activities()
    second = await service.list_activities()
    refreshed = await service.list_activities(refresh=True)

    assert first[0].activity_id == second[0].activity_id == refreshed[0].activity_id
    assert client.activity_list_calls == 2

    detail_client = FakeClient(fixture_json)
    detail_service = PuService(
        client=detail_client,
        storage=Storage(tmp_path / "detail.sqlite"),
        session_store=MemorySessionStore(),
    )
    detail = await detail_service.activity_detail("ACT-1001")
    cached_detail = await detail_service.activity_detail("ACT-1001")
    refreshed_detail = await detail_service.activity_detail("ACT-1001", refresh=True)

    assert detail.activity_id == cached_detail.activity_id == refreshed_detail.activity_id
    assert detail_client.activity_info_calls == 2


def test_service_schedule_defaults_to_one_attempt(tmp_path):
    service = PuService(
        client=None, storage=Storage(tmp_path / "pu.sqlite"), session_store=MemorySessionStore()
    )
    plan = service.create_signup_plan(
        "ACT-1001", "合成活动", datetime(2026, 6, 8, 18, 30, tzinfo=UTC)
    )
    assert plan.max_attempts == 1


def test_service_rejects_aggressive_attempt_count(tmp_path):
    service = PuService(
        client=None, storage=Storage(tmp_path / "pu.sqlite"), session_store=MemorySessionStore()
    )
    with pytest.raises(ValueError):
        service.create_signup_plan(
            "ACT-1001",
            "合成活动",
            datetime(2026, 6, 8, 18, 30, tzinfo=UTC),
            max_attempts=5,
        )


@pytest.mark.asyncio
async def test_service_skips_signup_if_already_joined(fixture_json, tmp_path):
    client = FakeClient(fixture_json)
    service = PuService(
        client=client, storage=Storage(tmp_path / "pu.sqlite"), session_store=MemorySessionStore()
    )
    plan = service.create_signup_plan("ACT-1009", "已报名合成活动", datetime.now(UTC))
    attempt = await service.execute_signup_plan(plan.plan_id)
    assert attempt.status == "skipped"
    assert client.join_calls == 0
