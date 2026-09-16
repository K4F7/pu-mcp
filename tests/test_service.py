from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pu_mcp.activity_parser import parse_activity
from pu_mcp.errors import BusinessError
from pu_mcp.models import AuthSession
from pu_mcp.service import PuService
from pu_mcp.storage import Storage


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
    def __init__(
        self,
        fixture_json,
        my_list_payload=None,
        my_list_handler=None,
        activity_list_payload=None,
        activity_info_handler=None,
    ):
        self.fixture_json = fixture_json
        self.my_list_payload = my_list_payload
        self.my_list_handler = my_list_handler
        self.activity_list_payload = activity_list_payload
        self.activity_info_handler = activity_info_handler
        self.my_list_calls = []
        self.join_calls = 0
        self.joined_activity_ids = []
        self.activity_list_calls = 0
        self.activity_list_filters = []
        self.activity_info_calls = 0
        self.activity_info_ids = []

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
        if self.activity_list_payload is not None:
            return self.activity_list_payload
        return self.fixture_json("activity_list.json")

    async def activity_info(self, activity_id):
        self.activity_info_calls += 1
        self.activity_info_ids.append(activity_id)
        if self.activity_info_handler is not None:
            return self.activity_info_handler(activity_id)
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
    payload = _joined_payload([_joined_item("ACT-2001", "签到合成活动", "校园文化", **fields)])
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
        _joined_item(f"ACT-P{index:02d}", f"分页活动{index}", "校园文化") for index in range(1, 22)
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

    assert [item.activity_id for item in joined] == [f"ACT-P{index:02d}" for index in range(1, 22)]
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
        {"type": 1, "page": 2, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_empty_type_still_merges_others(fixture_json, tmp_path):
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
        _joined_item(f"ACT-F{index:02d}", f"满页活动{index}", "校园文化") for index in range(1, 41)
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
    assert [item.activity_id for item in joined] == [f"ACT-F{index:02d}" for index in range(1, 41)]
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
        {"type": 1, "page": 2, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_full_page_without_page_info_stops(fixture_json, tmp_path):
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

    assert [item.activity_id for item in joined] == [f"ACT-N{index:02d}" for index in range(1, 21)]
    assert [call for call in client.my_list_calls if call["type"] == 1] == [
        {"type": 1, "page": 1, "limit": 20},
    ]


@pytest.mark.asyncio
async def test_service_joined_activities_unparsable_page_info_stops(fixture_json, tmp_path):
    type1_items = [
        _joined_item(f"ACT-G{index:02d}", f"垃圾分页{index}", "校园文化") for index in range(1, 21)
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


def _live_list_item(activity_id: object, name: str, **fields: object) -> dict:
    return {"id": activity_id, "name": name, "puType": 0, **fields}


def _live_info(
    activity_id: object,
    category_name: str | None,
    has_sign_in: int,
    name: str = "合成活动",
    *,
    description: str | None = None,
    address: str | None = None,
    status_name: str | None = None,
    status: object | None = None,
) -> dict:
    # Live PU activity/info omits data.id; callers pass list-side id separately.
    base_info: dict[str, object] = {"name": name}
    if category_name is not None:
        base_info["categoryName"] = category_name
    if description is not None:
        base_info["description"] = description
    if address is not None:
        base_info["address"] = address
    if status_name is not None:
        base_info["statusName"] = status_name
    if status is not None:
        base_info["status"] = status
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "puType": 0,
            "baseInfo": base_info,
            "userStatus": {"hasSignIn": has_sign_in, "hasJoin": 1},
        },
    }


def _live_info_by_id(details: dict[str, dict]) -> object:
    def handler(activity_id):
        return details[str(activity_id)]

    return handler


@pytest.mark.asyncio
async def test_list_activities_enriches_unknown_type_from_info(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "校园文化合成活动")]),
        activity_info_handler=lambda _id: _live_info(1001, "校园文化", 1, name="校园文化合成活动"),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert activities[0].activity_id == "1001"
    assert activities[0].activity_type == "校园文化"
    assert activities[0].signed_in is True
    assert client.activity_info_ids == ["1001"]


@pytest.mark.asyncio
async def test_joined_activities_enriches_unknown_type_from_info(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        my_list_payload=_joined_payload([_live_list_item(1001, "思想引领合成活动")]),
        activity_info_handler=lambda _id: _live_info(1001, "思想引领", 1, name="思想引领合成活动"),
    )
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert joined[0].activity_id == "1001"
    assert joined[0].activity_type == "思想引领"
    assert joined[0].signed_in is True
    assert client.activity_info_ids == ["1001"]


@pytest.mark.asyncio
async def test_list_activities_does_not_overwrite_known_type_via_enrichment(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_info_handler=lambda _id: _live_info(1001, "校园文化", 1),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert activities[0].activity_type == "志愿公益"


@pytest.mark.asyncio
async def test_joined_activities_does_not_overwrite_known_type_via_enrichment(
    fixture_json, tmp_path
):
    payload = _joined_payload([_joined_item("ACT-2001", "已知类型活动", "志愿公益", signedIn=True)])
    client = FakeClient(
        fixture_json,
        my_list_payload=payload,
        activity_info_handler=lambda _id: _live_info("ACT-2001", "校园文化", 0),
    )
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert joined[0].activity_type == "志愿公益"
    assert joined[0].signed_in is True


@pytest.mark.asyncio
async def test_enrichment_keeps_unknown_when_info_lacks_type(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1002, "未分类活动")]),
        my_list_payload=_joined_payload([_live_list_item(1002, "未分类活动")]),
        activity_info_handler=lambda _id: _live_info(1002, None, 1, name="未分类活动"),
    )
    service = _make_service(client, tmp_path)

    listed = await service.list_activities()
    joined = await service.joined_activities()

    assert listed[0].activity_type == "未知"
    assert joined[0].activity_type == "未知"
    assert listed[0].signed_in is True
    assert joined[0].signed_in is True


@pytest.mark.asyncio
async def test_list_activities_enrichment_survives_info_failure(fixture_json, tmp_path):
    class FailingInfoClient(FakeClient):
        async def activity_info(self, activity_id):
            self.activity_info_calls += 1
            self.activity_info_ids.append(activity_id)
            raise BusinessError('type mismatch for field "id"')

    client = FailingInfoClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "校园文化合成活动")]),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert activities[0].activity_type == "未知"
    assert activities[0].signed_in is False
    assert client.activity_info_calls == 1


@pytest.mark.asyncio
async def test_attendance_counts_from_live_my_list_via_info_enrichment(fixture_json, tmp_path):
    items = [
        _live_list_item(1, "实践已签"),
        _live_list_item(2, "实践未签"),
        _live_list_item(3, "文化已签"),
        _live_list_item(4, "讲座已签"),
        _live_list_item(5, "志愿已签"),
        _live_list_item(6, "双创已签"),
        _live_list_item(7, "公益已签"),
        _live_list_item(8, "未知已签"),
    ]
    details = {
        "1": _live_info(1, "社会实践", 1, name="实践已签"),
        "2": _live_info(2, "社会实践", 0, name="实践未签"),
        "3": _live_info(3, "校园文化", 1, name="文化已签"),
        "4": _live_info(4, "学术讲座", 1, name="讲座已签"),
        "5": _live_info(5, "志愿服务", 1, name="志愿已签"),
        "6": _live_info(6, "创新创业", 1, name="双创已签"),
        "7": _live_info(7, "志愿公益", 1, name="公益已签"),
        "8": _live_info(8, None, 1, name="未知已签"),
    }
    client = FakeClient(
        fixture_json,
        my_list_payload=_joined_payload(items),
        activity_info_handler=_live_info_by_id(details),
    )
    service = _make_service(client, tmp_path)

    counts = await service.attendance_counts()

    assert counts == {
        "社会实践": 1,
        "校园文化": 1,
        "思想引领": 0,
        "学科竞赛": 0,
        "学术讲座": 1,
        "体育健身": 0,
    }
    assert "志愿服务" not in counts
    assert "创新创业" not in counts
    assert "志愿公益" not in counts
    assert "未知" not in counts


@pytest.mark.asyncio
async def test_list_activities_not_poisoned_by_joined_detail_cache(fixture_json, tmp_path):
    catalog = [
        _live_list_item(2001, "目录活动甲"),
        _live_list_item(2002, "目录活动乙"),
    ]
    details = {
        "1001": _live_info(1001, "思想引领", 1, name="已报名活动"),
        "2001": _live_info(2001, "校园文化", 0, name="目录活动甲"),
        "2002": _live_info(2002, "学术讲座", 0, name="目录活动乙"),
    }
    client = FakeClient(
        fixture_json,
        my_list_payload=_joined_payload([_live_list_item(1001, "已报名活动")]),
        activity_list_payload=_joined_payload(catalog),
        activity_info_handler=_live_info_by_id(details),
    )
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()
    listed = await service.list_activities(refresh=False)

    assert [item.activity_id for item in joined] == ["1001"]
    assert [item.activity_id for item in listed] == ["2001", "2002"]
    assert client.activity_list_calls == 1
    cached_detail = await service.activity_detail("1001", refresh=False)
    assert cached_detail.activity_type == "思想引领"
    assert "baseInfo" in cached_detail.raw


@pytest.mark.asyncio
async def test_cached_list_shaped_unknown_later_fetches_info(fixture_json, tmp_path):
    fail_info = {"value": True}

    def handler(_activity_id):
        if fail_info["value"]:
            raise BusinessError("info unavailable")
        return _live_info(1001, "校园文化", 1, name="校园文化合成活动")

    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "校园文化合成活动")]),
        activity_info_handler=handler,
    )
    service = _make_service(client, tmp_path)

    first = await service.list_activities()
    assert first[0].activity_type == "未知"
    assert first[0].signed_in is False
    assert client.activity_info_calls == 1
    assert client.activity_list_calls == 1

    fail_info["value"] = False
    second = await service.list_activities()
    assert second[0].activity_type == "校园文化"
    assert second[0].signed_in is True
    assert client.activity_info_calls == 2
    assert client.activity_list_calls == 1

    third = await service.list_activities()
    assert third[0].activity_type == "校园文化"
    assert third[0].signed_in is True
    assert client.activity_info_calls == 2
    assert client.activity_list_calls == 1

    cached = service.storage.get_cached_activity("1001")
    assert cached is not None
    assert cached.activity_type == "校园文化"
    assert "baseInfo" in cached.raw


@pytest.mark.asyncio
async def test_list_activities_refresh_retries_info_for_list_shaped_unknown(fixture_json, tmp_path):
    fail_info = {"value": True}

    def handler(_activity_id):
        if fail_info["value"]:
            raise BusinessError("info unavailable")
        return _live_info(1001, "思想引领", 1, name="思想引领合成活动")

    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "思想引领合成活动")]),
        activity_info_handler=handler,
    )
    service = _make_service(client, tmp_path)

    first = await service.list_activities()
    assert first[0].activity_type == "未知"
    assert client.activity_info_calls == 1

    fail_info["value"] = False
    refreshed = await service.list_activities(refresh=True)
    assert refreshed[0].activity_type == "思想引领"
    assert refreshed[0].signed_in is True
    assert client.activity_info_calls == 2
    assert client.activity_list_calls == 2


@pytest.mark.asyncio
async def test_detail_shaped_unknown_does_not_refetch_info(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1002, "未分类活动")]),
        activity_info_handler=lambda _id: _live_info(1002, None, 1, name="未分类活动"),
    )
    service = _make_service(client, tmp_path)

    first = await service.list_activities()
    second = await service.list_activities()

    assert first[0].activity_type == "未知"
    assert first[0].signed_in is True
    assert second[0].activity_type == "未知"
    assert second[0].signed_in is True
    assert client.activity_info_calls == 1
    assert "baseInfo" in (service.storage.get_cached_activity("1002") or first[0]).raw


@pytest.mark.asyncio
async def test_activity_detail_skips_list_shaped_unknown_cache(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_info_handler=lambda _id: _live_info(1001, "校园文化", 1, name="校园文化合成活动"),
    )
    service = _make_service(client, tmp_path)
    service.storage.cache_activity(parse_activity(_live_list_item(1001, "校园文化合成活动")))

    detail = await service.activity_detail("1001", refresh=False)

    assert detail.activity_id == "1001"
    assert detail.activity_type == "校园文化"
    assert detail.signed_in is True
    assert client.activity_info_calls == 1
    assert "baseInfo" in detail.raw


@pytest.mark.asyncio
async def test_activity_detail_backfills_id_when_info_omits_id(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_info_handler=lambda _id: _live_info(1001, "校园文化", 1, name="校园文化合成活动"),
    )
    service = _make_service(client, tmp_path)

    detail = await service.activity_detail("1001")

    assert detail.activity_id == "1001"
    assert detail.title == "校园文化合成活动"
    assert detail.activity_type == "校园文化"
    assert detail.signed_in is True
    assert client.activity_info_ids == ["1001"]


@pytest.mark.asyncio
async def test_list_activities_skips_catalog_cache_for_noncanonical_page(fixture_json, tmp_path):
    client = FakeClient(fixture_json)
    service = _make_service(client, tmp_path)

    await service.list_activities(page=1, limit=20)
    await service.list_activities(page=2, limit=20)

    assert client.activity_list_calls == 2


@pytest.mark.asyncio
async def test_joined_enriches_sign_in_when_type_known_but_sign_missing(fixture_json, tmp_path):
    payload = _joined_payload([_joined_item("1001", "已知类型缺签到字段", "社会实践")])
    client = FakeClient(
        fixture_json,
        my_list_payload=payload,
        activity_info_handler=lambda _id: _live_info(
            1001, "校园文化", 1, name="已知类型缺签到字段"
        ),
    )
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()
    counts = await service.attendance_counts()

    assert joined[0].activity_type == "社会实践"
    assert joined[0].signed_in is True
    assert client.activity_info_calls >= 1
    assert counts["社会实践"] == 1
    assert counts["校园文化"] == 0


@pytest.mark.asyncio
async def test_enrichment_no_id_info_keeps_list_id_and_merges_type_sign_in(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "校园文化合成活动")]),
        my_list_payload=_joined_payload([_live_list_item(1001, "校园文化合成活动")]),
        activity_info_handler=lambda _id: _live_info(9999, "校园文化", 1, name="校园文化合成活动"),
    )
    service = _make_service(client, tmp_path)

    listed = await service.list_activities()
    joined = await service.joined_activities()

    assert listed[0].activity_id == "1001"
    assert listed[0].activity_type == "校园文化"
    assert listed[0].signed_in is True
    assert joined[0].activity_id == "1001"
    assert joined[0].activity_type == "校园文化"
    assert joined[0].signed_in is True


@pytest.mark.asyncio
async def test_enrichment_concurrent_preserves_order_and_merges(fixture_json, tmp_path):
    items = [
        _live_list_item(1, "活动甲"),
        _live_list_item(2, "活动乙"),
        _live_list_item(3, "活动丙"),
        _live_list_item(4, "活动丁"),
        _live_list_item(5, "活动戊"),
    ]
    details = {
        "1": _live_info(1, "社会实践", 1, name="活动甲"),
        "2": _live_info(2, "校园文化", 0, name="活动乙"),
        "3": _live_info(3, "思想引领", 1, name="活动丙"),
        "4": _live_info(4, "学术讲座", 1, name="活动丁"),
        "5": _live_info(5, "体育健身", 0, name="活动戊"),
    }
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload(items),
        activity_info_handler=_live_info_by_id(details),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert [item.activity_id for item in activities] == ["1", "2", "3", "4", "5"]
    assert [item.activity_type for item in activities] == [
        "社会实践",
        "校园文化",
        "思想引领",
        "学术讲座",
        "体育健身",
    ]
    assert [item.signed_in for item in activities] == [True, False, True, True, False]
    assert set(client.activity_info_ids) == {"1", "2", "3", "4", "5"}


@pytest.mark.asyncio
async def test_login_and_logout_clear_activity_caches(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "缓存活动")]),
        activity_info_handler=lambda _id: _live_info(1001, "校园文化", 1, name="缓存活动"),
    )
    service = _make_service(client, tmp_path)

    await service.list_activities()
    assert service.storage.get_cached_activity_list()
    await service.login("demo_user", "secret", school_sid="1")
    assert service.storage.get_cached_activity_list() == []

    await service.list_activities()
    assert service.storage.get_cached_activity_list()
    service.logout()
    assert service.storage.get_cached_activity_list() == []


def _complete_list_item(activity_id: str, title: str, activity_type: str, **fields: object) -> dict:
    payload = {
        "id": activity_id,
        "title": title,
        "typeName": activity_type,
        "description": "已有正文",
        "address": "虚构活动室 A",
        "statusName": "进行中",
        "status": 5,
        "hasSignIn": 1,
        "startTimeValue": "报名进行中",
        "joinStartTime": "2026-06-01 00:00:00",
    }
    payload.update(fields)
    return payload


@pytest.mark.asyncio
async def test_list_activities_enriches_content_location_status_from_info(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload(
            [_live_list_item(1001, "校园文化合成活动", typeName="校园文化", hasSignIn=1)]
        ),
        activity_info_handler=lambda _id: _live_info(
            1001,
            "思想引领",
            0,
            name="校园文化合成活动",
            description="活动正文",
            address="虚构活动室 A",
            status_name="未开始",
            status=21,
        ),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert activities[0].content == "活动正文"
    assert activities[0].location == "虚构活动室 A"
    assert activities[0].status == "未开始"
    assert activities[0].status_code == "21"
    assert activities[0].activity_type == "校园文化"
    assert activities[0].signed_in is True
    assert client.activity_info_calls == 1


@pytest.mark.asyncio
async def test_joined_activities_enriches_content_location_status_from_info(fixture_json, tmp_path):
    client = FakeClient(
        fixture_json,
        my_list_payload=_joined_payload(
            [_joined_item("1001", "已知类型活动", "志愿公益", signedIn=True)]
        ),
        activity_info_handler=lambda _id: _live_info(
            1001,
            "校园文化",
            0,
            name="已知类型活动",
            description="报名活动正文",
            address="虚构报告厅",
            status_name="进行中",
            status=5,
        ),
    )
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert joined[0].content == "报名活动正文"
    assert joined[0].location == "虚构报告厅"
    assert joined[0].status == "进行中"
    assert joined[0].status_code == "5"
    assert joined[0].activity_type == "志愿公益"
    assert joined[0].signed_in is True
    assert client.activity_info_calls == 1


@pytest.mark.asyncio
async def test_list_activities_enriches_when_only_signup_status_missing(fixture_json, tmp_path):
    """Complete list fields except signup_status still optional-enrich from info."""
    def info_handler(_id):
        payload = _live_info(
            "ACT-1001",
            "志愿公益",
            1,
            name="合成志愿服务活动",
            description="详情正文",
            address="详情地点",
            status_name="进行中",
            status=5,
        )
        payload["data"]["baseInfo"]["joinStartTime"] = "2026-06-01 00:00:00"
        payload["data"]["baseInfo"]["joinEndTime"] = "2026-12-31 23:59:59"
        payload["data"]["buttonInfo"] = [{"name": "报名", "event": "join"}]
        return payload

    incomplete = _complete_list_item("ACT-1001", "合成志愿服务活动", "志愿公益")
    incomplete.pop("startTimeValue", None)
    incomplete.pop("joinStartTime", None)
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([incomplete]),
        activity_info_handler=info_handler,
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert activities[0].signup_status == "报名进行中"
    assert activities[0].allow_signup is True
    assert client.activity_info_calls == 1


@pytest.mark.asyncio
async def test_list_activities_enriches_signup_state_from_info(fixture_json, tmp_path):
    def info_handler(_id):
        payload = _live_info(1001, "校园文化", 0, name="校园文化合成活动")
        payload["data"]["baseInfo"]["joinStartTime"] = "2026-06-01 00:00:00"
        payload["data"]["baseInfo"]["joinEndTime"] = "2026-12-31 23:59:59"
        payload["data"]["buttonInfo"] = [{"name": "报名", "event": "join"}]
        return payload

    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload([_live_list_item(1001, "校园文化合成活动")]),
        activity_info_handler=info_handler,
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert activities[0].activity_type == "校园文化"
    assert activities[0].signup_status == "报名进行中"
    assert activities[0].allow_signup is True
    assert activities[0].signup_start_time is not None
    assert activities[0].signup_end_time is not None
    assert client.activity_info_calls == 1


@pytest.mark.asyncio
async def test_list_activities_skips_info_when_content_location_status_present(
    fixture_json, tmp_path
):
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload(
            [_complete_list_item("ACT-1001", "合成志愿服务活动", "志愿公益")]
        ),
        activity_info_handler=lambda _id: _live_info(
            "ACT-1001",
            "校园文化",
            0,
            name="合成志愿服务活动",
            description="详情正文",
            address="详情地点",
            status_name="未开始",
            status=21,
        ),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert client.activity_info_calls == 0
    assert activities[0].content == "已有正文"
    assert activities[0].location == "虚构活动室 A"
    assert activities[0].status == "进行中"
    assert activities[0].status_code == "5"
    assert activities[0].activity_type == "志愿公益"


@pytest.mark.asyncio
async def test_joined_activities_skips_info_when_content_location_status_present(
    fixture_json, tmp_path
):
    client = FakeClient(
        fixture_json,
        my_list_payload=_joined_payload(
            [_complete_list_item("ACT-2001", "已知类型活动", "志愿公益")]
        ),
        activity_info_handler=lambda _id: _live_info(
            "ACT-2001",
            "校园文化",
            0,
            name="已知类型活动",
            description="详情正文",
            address="详情地点",
            status_name="未开始",
            status=21,
        ),
    )
    service = _make_service(client, tmp_path)

    joined = await service.joined_activities()

    assert client.activity_info_calls == 0
    assert joined[0].content == "已有正文"
    assert joined[0].location == "虚构活动室 A"
    assert joined[0].status == "进行中"
    assert joined[0].status_code == "5"
    assert joined[0].activity_type == "志愿公益"
    assert joined[0].signed_in is True


@pytest.mark.asyncio
async def test_enrichment_does_not_overwrite_known_status_or_location_with_empty(
    fixture_json, tmp_path
):
    payload = _joined_payload(
        [
            {
                "id": "ACT-1001",
                "title": "合成活动",
                "typeName": "志愿公益",
                "address": "虚构活动室 A",
                "status": "open",
                "hasSignIn": 1,
            }
        ]
    )
    client = FakeClient(
        fixture_json,
        activity_list_payload=payload,
        my_list_payload=payload,
        activity_info_handler=lambda _id: _live_info(
            "ACT-1001",
            "校园文化",
            0,
            name="合成活动",
            description="详情正文",
            address="",
            status_name="",
        ),
    )
    service = _make_service(client, tmp_path)

    listed = await service.list_activities()
    joined = await service.joined_activities()

    assert listed[0].status == "open"
    assert listed[0].status_code == "open"
    assert listed[0].location == "虚构活动室 A"
    assert listed[0].content == "详情正文"
    assert listed[0].activity_type == "志愿公益"
    assert listed[0].signed_in is True
    assert joined[0].status == "open"
    assert joined[0].location == "虚构活动室 A"
    assert joined[0].signed_in is True


@pytest.mark.asyncio
async def test_optional_enrichment_http_is_capped(fixture_json, tmp_path, monkeypatch):
    from pu_mcp import service as service_mod

    monkeypatch.setattr(service_mod, "ENRICH_OPTIONAL_HTTP_LIMIT", 2)
    items = [
        _joined_item(f"ACT-{index}", f"已知类型活动{index}", "校园文化", hasSignIn=1)
        for index in range(1, 6)
    ]
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload(items),
        activity_info_handler=lambda activity_id: _live_info(
            activity_id,
            "校园文化",
            1,
            name=f"已知类型活动{activity_id}",
            description=f"正文{activity_id}",
            address=f"地点{activity_id}",
            status_name="未开始",
            status=21,
        ),
    )
    service = _make_service(client, tmp_path)

    activities = await service.list_activities()

    assert client.activity_info_calls == 2
    filled = [item for item in activities if item.content]
    assert len(filled) == 2
    assert sum(1 for item in activities if item.content is None) == 3


@pytest.mark.asyncio
async def test_list_activities_filters_by_enriched_chinese_activity_type(fixture_json, tmp_path):
    """activity_type filter matches post-enrichment Chinese names, not raw list labels."""
    items = [
        _live_list_item(1001, "实践活动"),
        _live_list_item(1002, "文化活动"),
        _live_list_item(1003, "讲座活动"),
        _live_list_item(1004, "另一场文化"),
    ]
    details = {
        "1001": _live_info(1001, "社会实践", 0, name="实践活动"),
        "1002": _live_info(1002, "校园文化", 0, name="文化活动"),
        "1003": _live_info(1003, "学术讲座", 0, name="讲座活动"),
        "1004": _live_info(1004, "校园文化", 0, name="另一场文化"),
    }
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload(items),
        activity_info_handler=_live_info_by_id(details),
    )
    service = _make_service(client, tmp_path)

    filtered = await service.list_activities(activity_type="校园文化")

    assert [item.activity_id for item in filtered] == ["1002", "1004"]
    assert {item.activity_type for item in filtered} == {"校园文化"}
    # Client-side filter: PU API must not receive activity_type (Chinese label).
    assert client.activity_list_filters == [{"page": 1, "limit": 20}]


@pytest.mark.asyncio
async def test_list_activities_unknown_activity_type_filter_returns_empty(fixture_json, tmp_path):
    items = [
        _live_list_item(1001, "实践活动"),
        _live_list_item(1002, "文化活动"),
    ]
    details = {
        "1001": _live_info(1001, "社会实践", 0, name="实践活动"),
        "1002": _live_info(1002, "校园文化", 0, name="文化活动"),
    }
    client = FakeClient(
        fixture_json,
        activity_list_payload=_joined_payload(items),
        activity_info_handler=_live_info_by_id(details),
    )
    service = _make_service(client, tmp_path)

    filtered = await service.list_activities(activity_type="不存在的类型")

    assert filtered == []
    assert client.activity_list_filters == [{"page": 1, "limit": 20}]


@pytest.mark.asyncio
async def test_list_activities_activity_type_filter_uses_cache_then_filters(
    fixture_json, tmp_path
):
    items = [
        _complete_list_item("1001", "实践已完整", "社会实践"),
        _complete_list_item("1002", "文化已完整", "校园文化"),
        _complete_list_item("1003", "讲座已完整", "学术讲座"),
    ]
    client = FakeClient(fixture_json, activity_list_payload=_joined_payload(items))
    service = _make_service(client, tmp_path)

    await service.list_activities()  # populate catalog cache
    filtered = await service.list_activities(activity_type="学术讲座")

    assert [item.activity_id for item in filtered] == ["1003"]
    assert filtered[0].activity_type == "学术讲座"
    # First call fills cache; filtered call must not re-hit API with activity_type.
    assert client.activity_list_calls == 1
    assert client.activity_list_filters == [{"page": 1, "limit": 20}]
