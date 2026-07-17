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
