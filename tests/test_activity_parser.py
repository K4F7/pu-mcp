from __future__ import annotations

import pytest

from pu_tool.activity_parser import parse_activity_detail, parse_activity_list
from pu_tool.config import Settings
from pu_tool.models import SignupPlan


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
