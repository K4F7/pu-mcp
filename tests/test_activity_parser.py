from __future__ import annotations

from datetime import datetime

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
    assert activities[0].status == "已结束"
    assert activities[0].status_code == "23"


def test_parse_live_detail_flattens_category_name_and_has_sign_in(fixture_json):
    activity = parse_activity_detail(fixture_json("activity_info_live.json"), activity_id="1001")
    assert activity.activity_id == "1001"
    assert activity.title == "校园文化合成活动"
    assert activity.activity_type == "校园文化"
    assert activity.content == "合成活动说明正文"
    assert activity.location == "虚构活动室 A"
    assert activity.status == "未开始"
    assert activity.status_code == "21"
    assert activity.signed_in is True
    assert activity.activity_type != "0"


def test_parse_live_detail_without_id_raises_without_fallback(fixture_json):
    with pytest.raises(ParseError, match="id or title"):
        parse_activity_detail(fixture_json("activity_info_live.json"))


def test_parse_live_detail_backfills_requested_id(fixture_json):
    activity = parse_activity_detail(fixture_json("activity_info_live.json"), activity_id="4242")
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


def test_parse_prefers_description_over_empty_content():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "讲座",
            "description": "活动说明正文",
            "content": "",
        }
    )
    assert activity.content == "活动说明正文"


def test_parse_uses_content_when_description_empty():
    activity = parse_activity(
        {"id": "1001", "name": "讲座", "description": "", "content": "备用正文"}
    )
    assert activity.content == "备用正文"


def test_parse_empty_description_and_content_is_none():
    activity = parse_activity({"id": "1001", "name": "讲座", "description": "", "content": ""})
    assert activity.content is None


def test_parse_missing_description_and_content_is_none():
    activity = parse_activity({"id": "1001", "name": "讲座"})
    assert activity.content is None


def test_parse_nested_base_info_description_as_content():
    activity = parse_activity_detail(
        {
            "code": 0,
            "data": {
                "id": 1001,
                "baseInfo": {"name": "嵌套活动", "description": "嵌套说明正文"},
            },
        }
    )
    assert activity.content == "嵌套说明正文"


def test_parse_prefers_description_over_news_info_content():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "讲座",
            "newsInfo": {"content": "新闻正文"},
            "baseInfo": {"description": "活动说明正文", "name": "讲座"},
        }
    )
    assert activity.content == "活动说明正文"


def test_parse_does_not_flatten_news_info_content():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "讲座",
            "newsInfo": {"content": "新闻正文"},
            "baseInfo": {"name": "讲座"},
        }
    )
    assert activity.content is None
    assert activity.raw.get("newsInfo") == {"content": "新闻正文"}
    assert "content" not in activity.raw or activity.raw.get("content") in (None, "")


def test_parse_human_status_name_and_numeric_code():
    activity = parse_activity({"id": "1001", "name": "讲座", "statusName": "未开始", "status": 21})
    assert activity.status == "未开始"
    assert activity.status_code == "21"


def test_parse_human_status_name_snake_case():
    activity = parse_activity({"id": "1001", "name": "讲座", "status_name": "进行中", "status": 5})
    assert activity.status == "进行中"
    assert activity.status_code == "5"


def test_parse_numeric_status_only_is_status_code():
    activity = parse_activity({"id": "1001", "name": "讲座", "status": 23})
    assert activity.status == "已结束"
    assert activity.status_code == "23"


def test_parse_numeric_status_string_only_is_status_code():
    activity = parse_activity({"id": "1001", "name": "讲座", "status": "23"})
    assert activity.status == "已结束"
    assert activity.status_code == "23"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (5, "已结束"),
        ("5", "已结束"),
        (21, "未开始"),
        ("21", "未开始"),
        (22, "进行中"),
        ("22", "进行中"),
        (23, "已结束"),
        ("23", "已结束"),
    ],
)
def test_parse_maps_known_numeric_status_code_to_human_status(code, expected):
    activity = parse_activity({"id": "1001", "name": "讲座", "status": code})
    assert activity.status == expected
    assert activity.status_code == str(code)


def test_parse_unknown_numeric_status_code_stays_null():
    activity = parse_activity({"id": "1001", "name": "讲座", "status": 99})
    assert activity.status is None
    assert activity.status_code == "99"


def test_parse_empty_status_name_maps_ended_code_five():
    activity = parse_activity({"id": "1001", "name": "讲座", "statusName": "", "status": 5})
    assert activity.status == "已结束"
    assert activity.status_code == "5"


def test_parse_status_name_wins_over_conflicting_ended_code():
    activity = parse_activity({"id": "1001", "name": "讲座", "statusName": "进行中", "status": 5})
    assert activity.status == "进行中"
    assert activity.status_code == "5"


def test_parse_mapped_activity_status_is_not_signup_status():
    activity = parse_activity({"id": "1001", "name": "讲座", "status": 5})
    assert activity.status == "已结束"
    assert activity.signup_status is None
    assert activity.allow_signup is False


def test_parse_legacy_open_status_stays_in_status(fixture_json):
    activities = parse_activity_list(fixture_json("activity_list.json"))
    assert activities[0].status == "open"
    assert activities[0].status_code == "open"
    assert activities[1].status == "scheduled"
    assert activities[1].status_code == "scheduled"


def test_parse_live_detail_location_from_address(fixture_json):
    activity = parse_activity_detail(fixture_json("activity_info_live.json"), activity_id="1001")
    assert activity.location == "虚构活动室 A"


def test_parse_list_signup_ended_while_activity_in_progress(fixture_json):
    activities = parse_activity_list(fixture_json("activity_list_signup.json"))
    ended = activities[0]
    assert ended.activity_id == "ACT-3001"
    assert ended.status == "进行中"
    assert ended.signup_status == "报名已结束"
    assert ended.allow_signup is False
    assert ended.signup_start_time == datetime(2026, 6, 1, 0, 0, 0)


def test_parse_list_signup_in_progress_from_start_time_value(fixture_json):
    activities = parse_activity_list(fixture_json("activity_list_signup.json"))
    open_signup = activities[1]
    assert open_signup.status == "未开始"
    assert open_signup.signup_status == "报名进行中"
    assert open_signup.allow_signup is True


def test_parse_list_signup_not_started_from_start_time_value(fixture_json):
    activities = parse_activity_list(fixture_json("activity_list_signup.json"))
    pending = activities[2]
    assert pending.status == "未开始"
    assert pending.signup_status == "报名未开始"
    assert pending.allow_signup is False


def test_parse_join_start_and_end_time_aliases():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "报名窗口",
            "joinStartTime": "2026-06-08 18:30:00",
            "joinEndTime": "2026-06-09 18:30:00",
        }
    )
    assert activity.signup_start_time == datetime(2026, 6, 8, 18, 30, 0)
    assert activity.signup_end_time == datetime(2026, 6, 9, 18, 30, 0)


def test_parse_info_signup_open_from_button_join(fixture_json):
    activity = parse_activity_detail(
        fixture_json("activity_info_signup_open.json"), activity_id="4001"
    )
    assert activity.status == "未开始"
    assert activity.signup_status == "报名进行中"
    assert activity.allow_signup is True
    assert activity.signup_start_time == datetime(2026, 6, 1, 0, 0, 0)
    assert activity.signup_end_time == datetime(2026, 12, 31, 23, 59, 59)


def test_parse_info_signup_not_started_from_button_name(fixture_json):
    activity = parse_activity_detail(
        fixture_json("activity_info_signup_not_started.json"), activity_id="4002"
    )
    assert activity.signup_status == "报名未开始"
    assert activity.allow_signup is False


def test_parse_info_signup_ended_from_weibaoming_button(fixture_json):
    activity = parse_activity_detail(
        fixture_json("activity_info_signup_ended.json"), activity_id="4003"
    )
    assert activity.status == "进行中"
    assert activity.signup_status == "报名已结束"
    assert activity.allow_signup is False


def test_parse_button_info_single_dict_join_event():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "单按钮",
            "statusName": "未开始",
            "buttonInfo": {"name": "报名", "event": "join"},
        }
    )
    assert activity.signup_status == "报名进行中"
    assert activity.allow_signup is True


def test_allow_join_count_does_not_drive_allow_signup():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "不可靠名额",
            "statusName": "进行中",
            "startTimeValue": "报名已结束",
            "allowJoinCount": 99,
        }
    )
    assert activity.signup_status == "报名已结束"
    assert activity.allow_signup is False


def test_join_status_is_not_signup_status():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "用户已报",
            "statusName": "进行中",
            "startTimeValue": "报名已结束",
            "joinStatus": 1,
            "hasJoin": 1,
        }
    )
    assert activity.status == "进行中"
    assert activity.signup_status == "报名已结束"
    assert activity.allow_signup is False


def test_status_name_is_not_signup_status():
    activity = parse_activity({"id": "1001", "name": "讲座", "statusName": "进行中"})
    assert activity.status == "进行中"
    assert activity.signup_status is None
    assert activity.allow_signup is False


def test_numeric_start_time_value_is_not_signup_status():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "时间戳",
            "startTimeValue": 1718000000,
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.signup_status == "报名进行中"
    assert activity.allow_signup is True


def test_datetime_start_time_value_is_not_signup_status():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "时间文本",
            "startTimeValue": "2026-06-08 18:30:00",
            "buttonInfo": [{"name": "报名未开始", "event": ""}],
        }
    )
    assert activity.signup_status == "报名未开始"
    assert activity.allow_signup is False


def test_parse_signup_status_from_join_window_in_progress():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "窗口内",
            "joinStartTime": "2000-01-01 00:00:00",
            "joinEndTime": "2099-01-01 00:00:00",
        }
    )
    assert activity.signup_status == "报名进行中"
    assert activity.allow_signup is True


def test_parse_signup_status_from_join_window_not_started():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "窗口未开",
            "joinStartTime": "2099-01-01 00:00:00",
            "joinEndTime": "2099-12-31 00:00:00",
        }
    )
    assert activity.signup_status == "报名未开始"
    assert activity.allow_signup is False


def test_parse_signup_status_from_join_window_ended():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "窗口已关",
            "joinStartTime": "2000-01-01 00:00:00",
            "joinEndTime": "2000-01-31 00:00:00",
        }
    )
    assert activity.signup_status == "报名已结束"
    assert activity.allow_signup is False


def test_parse_signup_status_prefers_start_time_value_over_window():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "文案优先",
            "statusName": "进行中",
            "startTimeValue": "报名已结束",
            "joinStartTime": "2000-01-01 00:00:00",
            "joinEndTime": "2099-01-01 00:00:00",
        }
    )
    assert activity.status == "进行中"
    assert activity.signup_status == "报名已结束"
    assert activity.allow_signup is False


def test_parse_signup_status_uses_injected_now():
    payload = {
        "id": "1001",
        "name": "可注入现在",
        "joinStartTime": "2026-06-08 00:00:00",
        "joinEndTime": "2026-06-10 00:00:00",
    }
    before = parse_activity(payload, now=datetime(2026, 6, 7, 12, 0, 0))
    during = parse_activity(payload, now=datetime(2026, 6, 9, 12, 0, 0))
    after = parse_activity(payload, now=datetime(2026, 6, 11, 12, 0, 0))
    assert before.signup_status == "报名未开始"
    assert before.allow_signup is False
    assert during.signup_status == "报名进行中"
    assert during.allow_signup is True
    assert after.signup_status == "报名已结束"
    assert after.allow_signup is False


def test_parse_allow_year_and_college_names_from_base_info():
    activity = parse_activity(
        {
            "id": "378191869837313",
            "name": "考研择校择专业专题讲座",
            "baseInfo": {
                "allowYear": [{"name": "24", "id": 1}, {"name": "23"}],
                "allowCollege": [{"name": "软件与物联网工程学院"}],
            },
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.allowed_years == ["24", "23"]
    assert activity.allowed_colleges == ["软件与物联网工程学院"]


def test_parse_allow_year_from_flat_raw():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "扁平限制",
            "allowYear": [{"name": "24"}],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.allowed_years == ["24"]
    assert activity.allowed_colleges == []


def test_empty_allow_lists_mean_unrestricted_eligible_true():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "不限年级学院",
            "allowYear": [],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="任意学院",
    )
    assert activity.eligible is True
    assert activity.ineligible_reason is None
    assert activity.allow_signup is True


def test_year_mismatch_sets_eligible_false_and_blocks_allow_signup():
    activity = parse_activity(
        {
            "id": "378191869837313",
            "name": "考研讲座",
            "allowYear": [{"name": "24"}],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.eligible is False
    assert activity.ineligible_reason is not None
    assert "年级不符合参与条件" in activity.ineligible_reason
    assert activity.allow_signup is False


def test_college_mismatch_sets_eligible_false():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "学院限制",
            "allowYear": [],
            "allowCollege": [{"name": "计算机学院"}],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.eligible is False
    assert "学院不符合参与条件" in (activity.ineligible_reason or "")
    assert activity.allow_signup is False


def test_missing_user_year_with_restriction_leaves_eligible_none_but_window_allow():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "缺用户年级",
            "allowYear": [{"name": "24"}],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year=None,
        user_college=None,
    )
    assert activity.eligible is None
    assert activity.ineligible_reason is None
    assert activity.allow_signup is True  # eligible is not False


def test_known_mismatch_beats_missing_other_field():
    """Year fails even if college is missing while college is also restricted."""
    activity = parse_activity(
        {
            "id": "1001",
            "name": "双限制缺学院",
            "allowYear": [{"name": "24"}],
            "allowCollege": [{"name": "计算机学院"}],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college=None,
    )
    assert activity.eligible is False
    assert "年级不符合参与条件" in (activity.ineligible_reason or "")
    assert activity.allow_signup is False


def test_apply_eligibility_gates_existing_window_allow():
    from pu_mcp.activity_parser import apply_eligibility

    activity = parse_activity(
        {
            "id": "1001",
            "name": "后置资格",
            "allowYear": [{"name": "24"}],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.allow_signup is True
    gated = apply_eligibility(activity, user_year="25", user_college=None)
    assert gated.eligible is False
    assert gated.allow_signup is False
    assert "年级不符合参与条件" in (gated.ineligible_reason or "")


def test_missing_allow_keys_leave_eligible_unknown_not_unrestricted():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "列表无参与条件字段",
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.participation_rules_known is False
    assert activity.eligible is None
    assert activity.ineligible_reason is None
    assert activity.allow_signup is True


def test_empty_allow_keys_present_are_known_unrestricted():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "显式空限制",
            "allowYear": [],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.participation_rules_known is True
    assert activity.eligible is True
    assert activity.allow_signup is True


def test_only_allow_year_key_leaves_rules_unknown():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "仅有年级限制字段",
            "allowYear": [{"name": "24"}],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.participation_rules_known is False
    assert activity.eligible is None
    assert activity.allow_signup is True


def test_only_allow_college_key_leaves_rules_unknown():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "仅有学院限制字段",
            "allowCollege": [{"name": "计算机学院"}],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.participation_rules_known is False
    assert activity.eligible is None
    assert activity.allow_signup is True


def test_parse_capacity_and_joined_from_allow_user_count():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "名额活动",
            "allowUserCount": 30,
            "joinUserCount": 12,
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.capacity == 30
    assert activity.joined_count == 12
    assert activity.is_full is False
    assert activity.signup_status == "报名进行中"
    assert activity.allow_signup is True


def test_parse_capacity_snake_case_aliases():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "蛇形字段",
            "allow_user_count": 10,
            "join_user_count": 3,
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.capacity == 10
    assert activity.joined_count == 3
    assert activity.is_full is False


def test_parse_capacity_non_positive_is_none():
    for cap in (0, -1):
        activity = parse_activity(
            {
                "id": "1001",
                "name": "无限或不详",
                "allowUserCount": cap,
                "joinUserCount": 99,
                "buttonInfo": [{"name": "报名", "event": "join"}],
            }
        )
        assert activity.capacity is None
        assert activity.is_full is False
        assert activity.allow_signup is True


def test_parse_missing_capacity_fields_are_none():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "无名额",
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.capacity is None
    assert activity.joined_count is None
    assert activity.is_full is False


def test_full_capacity_gates_allow_signup_and_status_full():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "已满员",
            "allowUserCount": 50,
            "joinUserCount": 50,
            "buttonInfo": [{"name": "报名", "event": "join"}],
            "startTimeValue": "报名进行中",
        }
    )
    assert activity.is_full is True
    assert activity.allow_signup is False
    assert activity.signup_status == "已满"


def test_over_capacity_also_full():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "超员",
            "allowUserCount": 10,
            "joinUserCount": 11,
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.is_full is True
    assert activity.allow_signup is False
    assert activity.signup_status == "已满"


def test_full_does_not_change_not_started_status():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "未开报但已满",
            "allowUserCount": 5,
            "joinUserCount": 5,
            "startTimeValue": "报名未开始",
            "joinStartTime": "2099-01-01 00:00:00",
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.is_full is True
    assert activity.signup_status == "报名未开始"
    assert activity.allow_signup is False
    # eligible still computed for Agenda reservation filter
    assert activity.eligible is None or activity.eligible is True


def test_full_not_started_with_known_rules_keeps_eligible():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "未开报可预约",
            "allowUserCount": 5,
            "joinUserCount": 5,
            "startTimeValue": "报名未开始",
            "allowYear": [],
            "allowCollege": [],
        },
        user_year="25",
        user_college="软件与物联网工程学院",
    )
    assert activity.is_full is True
    assert activity.signup_status == "报名未开始"
    assert activity.allow_signup is False
    assert activity.eligible is True


def test_full_with_ineligible_still_false_allow():
    activity = parse_activity(
        {
            "id": "1001",
            "name": "满员且年级不符",
            "allowUserCount": 1,
            "joinUserCount": 1,
            "allowYear": [{"name": "24"}],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
        user_year="25",
    )
    assert activity.is_full is True
    assert activity.eligible is False
    assert activity.allow_signup is False
    assert activity.signup_status == "已满"


def test_capacity_from_nested_base_info(fixture_json):
    payload = {
        "code": 0,
        "msg": "ok",
        "data": {
            "baseInfo": {
                "name": "嵌套名额",
                "categoryName": "学术讲座",
                "allowUserCount": 20,
                "joinUserCount": 20,
                "statusName": "未开始",
                "status": 21,
            },
            "buttonInfo": [{"name": "报名", "event": "join"}],
        },
    }
    activity = parse_activity_detail(payload, activity_id="5001")
    assert activity.capacity == 20
    assert activity.joined_count == 20
    assert activity.is_full is True
    assert activity.signup_status == "已满"
    assert activity.allow_signup is False


def test_apply_eligibility_then_capacity_gate():
    from pu_mcp.activity_parser import apply_eligibility

    activity = parse_activity(
        {
            "id": "1001",
            "name": "后置满员",
            "allowUserCount": 2,
            "joinUserCount": 2,
            "allowYear": [],
            "allowCollege": [],
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.signup_status == "已满"
    assert activity.allow_signup is False
    gated = apply_eligibility(activity, user_year="25", user_college="X")
    assert gated.eligible is True
    assert gated.is_full is True
    assert gated.allow_signup is False
    assert gated.signup_status == "已满"


def test_allow_join_count_still_ignored_for_capacity():
    """allowJoinCount must not populate capacity (existing invariant)."""
    activity = parse_activity(
        {
            "id": "1001",
            "name": "别名干扰",
            "allowJoinCount": 99,
            "joinUserCount": 1,
            "buttonInfo": [{"name": "报名", "event": "join"}],
        }
    )
    assert activity.capacity is None
    assert activity.joined_count == 1
    assert activity.is_full is False
