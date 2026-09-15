from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pu_tool.errors import BusinessError
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
    def __init__(self, fixture_json, my_list_payload=None, my_list_handler=None):
        self.fixture_json = fixture_json
        self.my_list_payload = my_list_payload
        self.my_list_handler = my_list_handler
        self.my_list_calls = []
        self.join_calls = 0
        self.joined_activity_ids = []
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

    async def my_list(self, **filters):
        params = {"type": 1, "page": 1, "limit": 20, **filters}
        self.my_list_calls.append(params)
        if self.my_list_handler is not None:
            return self.my_list_handler(params["type"], params["page"], params["limit"])
        if self.my_list_payload is not None:
            return self.my_list_payload
        return self.fixture_json("my_list_joined.json")

    async def join_activity(self, activity_id):
        self.join_calls += 1
        self.joined_activity_ids.append(activity_id)
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
async def test_service_list_activities_does_not_filter_volunteer_or_non_gap_types(
    fixture_json, tmp_path
):
    service = _make_service(FakeClient(fixture_json), tmp_path)
    activities = await service.list_activities()
    types = {item.activity_type for item in activities}
    assert "志愿公益" in types
    assert "学术讲座" in types


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


def _make_service(client, tmp_path) -> PuService:
    return PuService(
        client=client,
        storage=Storage(tmp_path / "pu.sqlite"),
        session_store=MemorySessionStore(),
    )


@pytest.mark.asyncio
async def test_service_join_activity_forwards_to_client_and_returns_payload(fixture_json, tmp_path):
    client = FakeClient(fixture_json)
    service = _make_service(client, tmp_path)

    result = await service.join_activity("ACT-1001")

    assert client.join_calls == 1
    assert client.joined_activity_ids == ["ACT-1001"]
    assert result == {"code": 0, "msg": "报名成功"}


@pytest.mark.asyncio
async def test_service_join_activity_propagates_business_error(fixture_json, tmp_path):
    class FailingClient(FakeClient):
        async def join_activity(self, activity_id):
            self.join_calls += 1
            self.joined_activity_ids.append(activity_id)
            raise BusinessError("已报名该活动")

    client = FailingClient(fixture_json)
    service = _make_service(client, tmp_path)

    with pytest.raises(BusinessError, match="已报名该活动"):
        await service.join_activity("ACT-1001")
    assert client.join_calls == 1
    assert client.joined_activity_ids == ["ACT-1001"]


def _page_info(page: int, limit: int, total: int) -> dict:
    total_page = (total + limit - 1) // limit if total else 0
    return {"page": page, "limit": limit, "total": total, "totalPage": total_page}


def _joined_payload(items: list[dict], page_info: dict | None = None) -> dict:
    data: dict = {"list": items}
    if page_info is not None:
        data["pageInfo"] = page_info
    return {"code": 0, "msg": "ok", "data": data}


def _joined_item(activity_id: str, title: str, activity_type: str, **fields: object) -> dict:
    return {"id": activity_id, "title": title, "typeName": activity_type, **fields}


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"signedIn": True}, True),
        ({"signed_in": True}, True),
        ({"isSign": "1"}, True),
        ({"is_sign": "true"}, True),
        ({"hasSign": "True"}, True),
        ({"has_sign": "yes"}, True),
        ({"signStatus": "YES"}, True),
        ({"sign_status": "已签到"}, True),
        ({"signIn": "现场已签到完成"}, True),
        ({"sign_in": False}, False),
        ({"signedIn": "0"}, False),
        ({"signedIn": "false"}, False),
        ({"signedIn": "False"}, False),
        ({"signedIn": "no"}, False),
        ({"signedIn": "NO"}, False),
        ({"signedIn": "未签到"}, False),
        ({"status": "已签到"}, True),
        ({"state": "活动已签到"}, True),
        ({}, False),
        ({"signedIn": False, "status": "已签到"}, False),
    ],
)
@pytest.mark.asyncio
async def test_service_joined_activities_parse_signed_in_from_pu_fields(
    fixture_json, tmp_path, fields, expected
):
    payload = _joined_payload(
        [_joined_item("ACT-2001", "签到合成活动", "校园文化", **fields)]
    )
    service = _make_service(FakeClient(fixture_json, my_list_payload=payload), tmp_path)

    joined = await service.joined_activities()

    assert joined[0].signed_in is expected


@pytest.mark.asyncio
async def test_service_attendance_counts_signed_in_countable_types_only(fixture_json, tmp_path):
    payload = _joined_payload(
        [
            _joined_item("A1", "实践已签", "社会实践", signedIn=True),
            _joined_item("A2", "实践未签", "社会实践", signedIn=False),
            _joined_item("A3", "文化已签", "校园文化", isSign="1"),
            _joined_item("A4", "引领已签", "思想引领", signStatus="已签到"),
            _joined_item("A5", "讲座已签", "学术讲座", signed_in="true"),
            _joined_item("A6", "讲座再签", "学术讲座", hasSign=True),
            _joined_item("A7", "志愿已签", "志愿服务", signedIn=True),
            _joined_item("A8", "双创已签", "创新创业", signedIn=True),
            _joined_item("A9", "公益已签", "志愿公益", signedIn=True),
            _joined_item("A10", "文化未签", "校园文化"),
        ]
    )
    service = _make_service(FakeClient(fixture_json, my_list_payload=payload), tmp_path)

    counts = await service.attendance_counts()

    assert counts == {
        "社会实践": 1,
        "校园文化": 1,
        "思想引领": 1,
        "学科竞赛": 0,
        "学术讲座": 2,
        "体育健身": 0,
    }
    forbidden = (
        "credits",
        "effective",
        "must_fill",
        "必须补",
        "已获",
        "总有效分",
        "阶段线",
        "recommended_types",
        "recommended",
        "fillable",
    )
    blob = str(counts)
    assert all(token not in blob for token in forbidden)
    assert set(counts) == {
        "社会实践",
        "校园文化",
        "思想引领",
        "学科竞赛",
        "学术讲座",
        "体育健身",
    }


@pytest.mark.asyncio
async def test_service_joined_activities_empty_list_is_success(fixture_json, tmp_path):
    def handler(list_type, page, limit):
        return _joined_payload([], _page_info(page, limit, 0))

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert joined == []


@pytest.mark.asyncio
async def test_service_joined_activities_merges_types_1_to_3(fixture_json, tmp_path):
    items = {
        1: [_joined_item("ACT-T1", "已报名类型1", "校园文化")],
        2: [_joined_item("ACT-T2", "已报名类型2", "学术讲座")],
        3: [
            _joined_item("ACT-T3", "已报名类型3", "体育健身"),
            _joined_item("ACT-T1", "重复的类型1活动", "校园文化"),
        ],
    }

    def handler(list_type, page, limit):
        rows = items.get(list_type, [])
        return _joined_payload(rows, _page_info(page, limit, len(rows)))

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert [item.activity_id for item in joined] == ["ACT-T1", "ACT-T2", "ACT-T3"]
    requested_types = [call["type"] for call in client.my_list_calls]
    assert requested_types == [1, 2, 3]
    assert all(call["page"] == 1 and call["limit"] == 20 for call in client.my_list_calls)
    assert 0 not in requested_types
    assert 4 not in requested_types


@pytest.mark.asyncio
async def test_service_joined_activities_paginates_via_page_info(fixture_json, tmp_path):
    type1_items = [
        _joined_item(f"ACT-P{index:02d}", f"分页活动{index}", "校园文化")
        for index in range(1, 22)
    ]

    def handler(list_type, page, limit):
        if list_type != 1:
            return _joined_payload([], _page_info(page, limit, 0))
        start = (page - 1) * limit
        chunk = type1_items[start : start + limit]
        return _joined_payload(chunk, _page_info(page, limit, len(type1_items)))

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert [item.activity_id for item in joined] == [
        f"ACT-P{index:02d}" for index in range(1, 22)
    ]
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
        {"type": 1, "page": 2, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_empty_type_still_merges_others(
    fixture_json, tmp_path
):
    items = {
        1: [],
        2: [_joined_item("ACT-E2", "类型2活动", "学术讲座")],
        3: [_joined_item("ACT-E3", "类型3活动", "体育健身")],
    }

    def handler(list_type, page, limit):
        rows = items.get(list_type, [])
        return _joined_payload(rows, _page_info(page, limit, len(rows)))

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert [item.activity_id for item in joined] == ["ACT-E2", "ACT-E3"]
    assert [call["type"] for call in client.my_list_calls] == [1, 2, 3]


@pytest.mark.asyncio
async def test_service_joined_activities_stops_on_full_last_page_via_page_info(
    fixture_json, tmp_path
):
    type1_items = [
        _joined_item(f"ACT-F{index:02d}", f"满页活动{index}", "校园文化")
        for index in range(1, 41)
    ]

    def handler(list_type, page, limit):
        if list_type != 1:
            return _joined_payload([], _page_info(page, limit, 0))
        if page >= 3:
            raise AssertionError(f"type=1 page={page} should not be requested")
        start = (page - 1) * limit
        chunk = type1_items[start : start + limit]
        return _joined_payload(chunk, _page_info(page, limit, 40))

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert len(joined) == 40
    assert len({item.activity_id for item in joined}) == 40
    assert [item.activity_id for item in joined] == [
        f"ACT-F{index:02d}" for index in range(1, 41)
    ]
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
        {"type": 1, "page": 2, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_full_page_without_page_info_stops(
    fixture_json, tmp_path
):
    type1_items = [
        _joined_item(f"ACT-N{index:02d}", f"无分页信息{index}", "校园文化")
        for index in range(1, 21)
    ]

    def handler(list_type, page, limit):
        if list_type != 1:
            return _joined_payload([], _page_info(page, limit, 0))
        if page >= 2:
            raise AssertionError("full page without pageInfo should stop")
        return _joined_payload(type1_items)

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert [item.activity_id for item in joined] == [
        f"ACT-N{index:02d}" for index in range(1, 21)
    ]
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_unparsable_page_info_stops(
    fixture_json, tmp_path
):
    type1_items = [
        _joined_item(f"ACT-G{index:02d}", f"垃圾分页{index}", "校园文化")
        for index in range(1, 21)
    ]

    def handler(list_type, page, limit):
        if list_type != 1:
            return _joined_payload([], _page_info(page, limit, 0))
        if page >= 2:
            raise AssertionError("unparsable pageInfo should be treated as missing")
        return _joined_payload(
            type1_items,
            {"page": "x", "limit": "y", "total": "lots", "totalPage": "n/a"},
        )

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert len(joined) == 20
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_caps_pages_per_list_type(fixture_json, tmp_path):
    def handler(list_type, page, limit):
        if list_type != 1:
            return _joined_payload([], _page_info(page, limit, 0))
        if page > 50:
            raise AssertionError("buggy pageInfo must not paginate past the safety cap")
        items = [
            _joined_item(f"ACT-C{page:02d}-{index:02d}", f"帽页{page}-{index}", "校园文化")
            for index in range(1, limit + 1)
        ]
        return _joined_payload(
            items,
            {"page": page, "limit": limit, "total": 99999, "totalPage": 999},
        )

    client = FakeClient(fixture_json, my_list_handler=handler)
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    type1_calls = [call for call in client.my_list_calls if call["type"] == 1]
    assert len(type1_calls) == 50
    assert type1_calls[0] == {"type": 1, "page": 1, "limit": 20}
    assert type1_calls[-1] == {"type": 1, "page": 50, "limit": 20}
    assert len(joined) == 50 * 20
