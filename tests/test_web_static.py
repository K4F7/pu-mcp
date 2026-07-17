from pathlib import Path

STATIC_PATH = Path(__file__).parents[1] / "src" / "pu_tool" / "web_static"
APP_TS = STATIC_PATH / "app.ts"
APP_JS = STATIC_PATH / "app.js"


def test_static_js_uses_safe_dom_rendering_helpers():
    source = APP_TS.read_text(encoding="utf-8")
    assert "function textCell" in source
    assert "textContent" in source
    assert "encodeURIComponent(activity.activity_id)" in source
    assert "function renderPlans" in source
    assert "/api/signup/plans" in source
    assert 'method:"DELETE"' in source
    assert "if(x==null||x===false)return" in source


def test_static_js_does_not_interpolate_untrusted_activity_fields_into_inner_html():
    source = APP_TS.read_text(encoding="utf-8")
    forbidden = [
        "${activity.title}",
        "${activity.activity_id}",
        "${activity.activity_type}",
        "${attempt.message}",
        "${plan.activity_title}",
    ]
    for pattern in forbidden:
        assert pattern not in source


def test_static_js_submits_datetime_local_as_iso_string():
    source = APP_TS.read_text(encoding="utf-8")
    assert "new Date(runAt.value).toISOString()" in source


def test_settings_login_collects_school_identifier_and_shows_server_message():
    source = APP_TS.read_text(encoding="utf-8")
    assert "loginSchoolPayload(school.value)" in source
    assert "学校 SID 或 class 登录链接" in source
    assert "data?.error?.message" in source


def test_activity_list_links_to_details_and_exposes_discovery_filters():
    source = APP_TS.read_text(encoding="utf-8")
    for token in (
        "filterActivities",
        "搜索标题、ID、地点或组织方",
        "活动类型",
        "活动状态",
        "显示 ${x.length} / ${a.length} 个活动",
        "`/activities/${encodeURIComponent(i.activity_id)}`",
    ):
        assert token in source


def test_activity_detail_shows_participation_information_and_plan_feedback():
    source = APP_TS.read_text(encoding="utf-8")
    for label in ("活动时间", "报名窗口", "地点", "组织方", "奖励", "活动 ID"):
        assert label in source
    assert "计划已创建。" in source
    assert "前往计划页" in source


def test_reminders_static_contract_is_safe_and_retries():
    source = (STATIC_PATH / "reminders.ts").read_text(encoding="utf-8")
    tokens = (
        "/api/reminders",
        "60000",
        "15000",
        "textContent",
        "replaceChildren",
        "retry.onclick = load",
        "updateCountdowns",
    )
    for token in tokens:
        assert token in source
    assert "innerHTML" not in source


def test_reminder_countdown_contract_covers_start_end_and_unknown_times():
    source = (STATIC_PATH / "reminder_time.ts").read_text(encoding="utf-8")
    messages = (
        "分钟开始",
        "分钟结束",
        "活动已结束",
        "结束时间未知",
        "无法计算开始时间",
    )
    for message in messages:
        assert message in source


def test_reminders_bundle_is_minified_and_contains_calendar_views():
    source = (APP_JS.parent / "reminders.js").read_text(encoding="utf-8")
    assert "dayGridMonth" in source and "listMonth" in source
