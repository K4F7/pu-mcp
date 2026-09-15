from pathlib import Path

APP_JS = Path(__file__).parents[1] / "src" / "pu_mcp" / "web_static" / "app.js"


def test_static_js_uses_safe_dom_rendering_helpers():
    source = APP_JS.read_text(encoding="utf-8")
    assert "function textCell" in source
    assert "textContent" in source
    assert "encodeURIComponent(activity.activity_id)" in source
    assert "function renderPlans" in source
    assert "/api/signup/plans" in source
    assert "method: \"DELETE\"" in source


def test_static_js_does_not_interpolate_untrusted_activity_fields_into_inner_html():
    source = APP_JS.read_text(encoding="utf-8")
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
    source = APP_JS.read_text(encoding="utf-8")
    assert "new Date(runAt.value).toISOString()" in source
