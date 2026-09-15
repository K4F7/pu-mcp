from __future__ import annotations

import pytest

from pu_mcp.activity_parser import parse_activity, parse_activity_detail, parse_activity_list
from pu_mcp.config import Settings
from pu_mcp.errors import ParseError
from pu_mcp.models import SignupPlan


def test_settings_defaults_are_conservative():
    settings = Settings()
    assert settings.base_url == "https://apis.pocketuni.net"
    assert settings.web_host == "127.0.0.1"
    assert settings.max_retries == 2
    assert settings.max_signup_attempts == 3


def test_signup_plan_rejects_aggressive_attempt_counts():
    with pytest.raises(ValueError):
        SignupPlan(
            activity_id="ACT-1001", activity_title="x", run_at="2026-06-08T18:30:00", max_attempts=4
        )


def test_parse_activity_list_extracts_type_and_score_summary(fixture_json):
    activities = parse_activity_list(fixture_json("activity_list.json"))
    first = activities[0]
    assert first.activity_id == "ACT-1001"
    assert first.activity_type == "志愿公益"
    assert {item.kind for item in first.score_items} >= {"credit", "academic_credit", "point"}


def test_parse_activity_detail_preserves_unknown_reward_fields(fixture_json):
    activity = parse_activity_detail(fixture_json("activity_info_credit.json"))
    assert activity.activity_type == "志愿公益"
    assert any(
        item.kind == "unknown" and item.source_field == "unknownReward"
        for item in activity.score_items
    )
    assert "unknownReward" in activity.raw


def test_parse_activity_list_coerces_int_status_from_my_list(fixture_json):
    activities = parse_activity_list(fixture_json("my_list_joined.json"))
    assert activities[0].activity_id == "ACT-1009"
    assert activities[0].status == "23"


def test_parse_live_detail_flattens_category_name_and_has_sign_in(fixture_json):
    activity = parse_activity_detail(
        fixture_json("activity_info_live.json"), activity_id="1001"
    )
    assert activity.activity_id == "1001"
    assert activity.title == "校园文化合成活动"
    assert activity.activity_type == "校园文化"
    assert activity.signed_in is True
    assert activity.activity_type != "0"


def test_parse_live_detail_without_id_raises_without_fallback(fixture_json):
    with pytest.raises(ParseError, match="id or title"):
        parse_activity_detail(fixture_json("activity_info_live.json"))


def test_parse_live_detail_backfills_requested_id(fixture_json):
    activity = parse_activity_detail(
        fixture_json("activity_info_live.json"), activity_id="4242"
    )
    assert activity.activity_id == "4242"
    assert activity.title == "校园文化合成活动"
    assert activity.activity_type == "校园文化"
    assert activity.signed_in is True


def test_parse_live_detail_has_sign_in_zero_is_false(fixture_json):
    payload = fixture_json("activity_info_live.json")
    payload["data"]["userStatus"]["hasSignIn"] = 0
    activity = parse_activity_detail(payload, activity_id="1001")
    assert activity.activity_id == "1001"
    assert activity.activity_type == "校园文化"
    assert activity.signed_in is False


def test_parse_live_list_item_without_type_fields_is_unknown():
    payload = {
        "code": 0,
        "data": {"list": [{"id": 1001, "name": "校园文化合成活动", "puType": 0}]},
    }
    activities = parse_activity_list(payload)
    assert activities[0].activity_id == "1001"
    assert activities[0].title == "校园文化合成活动"
    assert activities[0].activity_type == "未知"
    assert activities[0].signed_in is False


def test_parse_does_not_map_putype_zero_to_activity_type():
    activity = parse_activity({"id": "1001", "name": "无类型活动", "puType": 0})
    assert activity.activity_type == "未知"


def test_parse_category_name_field_at_top_level():
    activity = parse_activity({"id": "1001", "name": "讲座", "categoryName": "学术讲座"})
    assert activity.activity_type == "学术讲座"


def test_parse_category_name_snake_case_field():
    activity = parse_activity({"id": "1001", "name": "讲座", "category_name": "思想引领"})
    assert activity.activity_type == "思想引领"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, True),
        (0, False),
        ("1", True),
        ("0", False),
    ],
)
def test_parse_has_sign_in_int_and_string_flags(value, expected):
    activity = parse_activity(
        {"id": "1001", "name": "签到活动", "typeName": "校园文化", "hasSignIn": value}
    )
    assert activity.signed_in is expected


def test_parse_has_sign_in_snake_case_int():
    activity = parse_activity(
        {"id": "1001", "name": "签到活动", "typeName": "校园文化", "has_sign_in": 1}
    )
    assert activity.signed_in is True


def test_parse_nested_info_without_category_name_stays_unknown():
    activity = parse_activity_detail(
        {
            "code": 0,
            "data": {
                "id": 1002,
                "puType": 0,
                "baseInfo": {"name": "未分类活动"},
                "userStatus": {"hasSignIn": 1, "hasJoin": 1},
            },
        }
    )
    assert activity.title == "未分类活动"
    assert activity.activity_type == "未知"
    assert activity.signed_in is True


def test_parse_keeps_outer_id_when_flattening_nested_info():
    activity = parse_activity_detail(
        {
            "code": 0,
            "data": {
                "id": 2002,
                "baseInfo": {"id": 999, "name": "外层 id 优先", "categoryName": "学科竞赛"},
                "userStatus": {"hasSignIn": 0, "hasJoin": 1},
            },
        }
    )
    assert activity.activity_id == "2002"
    assert activity.activity_type == "学科竞赛"
    assert activity.signed_in is False


def test_parse_detail_fallback_id_does_not_override_outer_id():
    activity = parse_activity_detail(
        {
            "code": 0,
            "data": {
                "id": 2002,
                "baseInfo": {"id": 999, "name": "外层 id 优先", "categoryName": "学科竞赛"},
                "userStatus": {"hasSignIn": 0, "hasJoin": 1},
            },
        },
        activity_id="requested-should-not-win",
    )
    assert activity.activity_id == "2002"


def test_parse_does_not_stringify_nested_base_info_as_type():
    activity = parse_activity_detail(
        {
            "code": 0,
            "data": {
                "id": 1001,
                "baseInfo": {"name": "嵌套活动", "categoryName": "体育健身"},
                "userStatus": {"hasSignIn": 1},
            },
        }
    )
    assert activity.activity_type == "体育健身"
    assert not activity.activity_type.startswith("{")
    assert activity.signed_in is True
