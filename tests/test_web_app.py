from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

import pu_tool.web_app as web_app
from pu_tool.errors import (
    AuthError,
    BusinessError,
    NetworkError,
    RateLimitError,
    RiskControlError,
)
from pu_tool.models import Activity, ScoreItem, SignupPlan
from pu_tool.web_app import create_app


class MockService:
    def auth_status(self):
        return {"authenticated": False, "message": "仅用于本人账号"}

    async def list_activities(self, **_filters):
        return [
            Activity(
                activity_id="ACT-1001",
                title="合成志愿服务活动",
                activity_type="志愿公益",
                score_items=[
                    ScoreItem(
                        kind="point", label="积分", value="10", unit="分", source_field="point"
                    )
                ],
            )
        ]

    async def activity_detail(self, activity_id, refresh=False):
        return (await self.list_activities())[0]

    async def joined_activities(self):
        return []

    async def login(self, username, password, school_sid):
        from pu_tool.models import AuthSession

        self.login_call = {
            "username": username,
            "password": password,
            "school_sid": school_sid,
        }
        return AuthSession(
            token="test-token-abcdef123456", sid="test-sid-654321", masked_user=username
        )

    def logout(self):
        return None

    def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
        return SignupPlan(
            plan_id=1,
            activity_id=activity_id,
            activity_title=activity_title,
            run_at=run_at,
            max_attempts=max_attempts,
        )

    def list_signup_plans(self):
        return [
            SignupPlan(
                plan_id=1,
                activity_id="ACT-1001",
                activity_title="合成志愿服务活动",
                run_at=datetime.now(UTC),
            )
        ]

    def cancel_signup_plan(self, plan_id):
        return self.list_signup_plans()[0].model_copy(
            update={"status": "cancelled", "enabled": False}
        )

    def list_signup_attempts(self, plan_id=None):
        return []


def test_web_api_activities_show_type_and_score():
    client = TestClient(create_app(MockService()))
    response = client.get("/api/activities")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["activity_type"] == "志愿公益"
    assert data[0]["score_items"][0]["label"] == "积分"


def test_web_pages_include_compliance_boundary():
    client = TestClient(create_app(MockService()))
    response = client.get("/")
    assert response.status_code == 200
    assert "仅用于本人账号" in response.text


def test_web_signup_plan_api():
    client = TestClient(create_app(MockService()))
    response = client.post(
        "/api/signup/plans",
        json={
            "activity_id": "ACT-1001",
            "activity_title": "合成活动",
            "run_at": "2026-06-08T18:30:00+00:00",
        },
    )
    assert response.status_code == 200
    assert response.json()["max_attempts"] == 1


def test_default_web_app_reuses_single_service(monkeypatch):
    created = []

    def fake_build_service():
        service = MockService()
        created.append(service)
        return service

    monkeypatch.setattr(web_app, "build_service", fake_build_service)
    client = TestClient(create_app())
    assert client.get("/api/auth/status").status_code == 200
    assert client.get("/api/auth/status").status_code == 200
    assert len(created) == 1


def test_web_auth_login_uses_school_sid_without_leaking_password():
    service = MockService()
    client = TestClient(create_app(service))
    response = client.post(
        "/api/auth/login",
        json={
            "username": "fake-number",
            "password": "fake-password",
            "sid": "237791864815616",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "user": "fake-number"}
    assert service.login_call == {
        "username": "fake-number",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "fake-password" not in response.text


def test_web_auth_login_decodes_encoded_sid():
    service = MockService()
    client = TestClient(create_app(service))
    response = client.post(
        "/api/auth/login",
        json={
            "username": "fake-number",
            "password": "fake-password",
            "encoded_sid": "QVpTRFBVS19QS1hRRVhS",
        },
    )

    assert response.status_code == 200
    assert service.login_call["school_sid"] == "237791864815616"


def test_web_auth_web_login_route_is_removed():
    client = TestClient(create_app(MockService()))
    response = client.post(
        "/api/auth/web-login",
        json={"sid": "588", "number": "fake-number", "password": "fake-password"},
    )

    assert response.status_code == 404
    assert "fake-password" not in response.text


def test_web_signup_plan_registers_and_cancels_scheduler():
    class RecordingScheduler:
        def __init__(self):
            self.registered = []
            self.cancelled = []

        def start(self):
            return None

        def stop(self):
            return None

        def register_plan(self, plan_id, run_at):
            self.registered.append((plan_id, run_at))

        def cancel_plan(self, plan_id):
            self.cancelled.append(plan_id)

    scheduler = RecordingScheduler()
    client = TestClient(create_app(MockService(), scheduler=scheduler))
    response = client.post(
        "/api/signup/plans",
        json={
            "activity_id": "ACT-1001",
            "activity_title": "合成活动",
            "run_at": "2026-06-08T18:30:00+00:00",
        },
    )
    assert response.status_code == 200
    assert scheduler.registered == [(1, datetime(2026, 6, 8, 18, 30, tzinfo=UTC))]

    response = client.delete("/api/signup/plans/1")
    assert response.status_code == 200
    assert scheduler.cancelled == [1]


def test_web_signup_plan_normalizes_naive_run_at_before_storage_and_scheduler():
    captured = {}

    class CapturingService(MockService):
        def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
            captured["service_run_at"] = run_at
            return super().create_signup_plan(activity_id, activity_title, run_at, max_attempts)

    class RecordingScheduler:
        def __init__(self):
            self.registered = []

        def start(self):
            return None

        def stop(self):
            return None

        def register_plan(self, plan_id, run_at):
            self.registered.append((plan_id, run_at))

    scheduler = RecordingScheduler()
    client = TestClient(create_app(CapturingService(), scheduler=scheduler))
    response = client.post(
        "/api/signup/plans",
        json={
            "activity_id": "ACT-1001",
            "activity_title": "合成活动",
            "run_at": "2026-06-08T18:30:00",
        },
    )

    assert response.status_code == 200
    assert captured["service_run_at"].tzinfo is not None
    assert captured["service_run_at"].utcoffset() is not None
    assert scheduler.registered[0][1].tzinfo is not None
    assert scheduler.registered[0][1].utcoffset() is not None


def test_web_error_handler_returns_unified_json():
    class ErrorService(MockService):
        async def login(self, username, password, school_sid):
            raise AuthError("session expired")

        async def list_activities(self, **_filters):
            raise NetworkError("offline")

        def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
            raise RateLimitError("too many")

        def cancel_signup_plan(self, plan_id):
            raise KeyError(f"signup plan not found: {plan_id}")

    client = TestClient(create_app(ErrorService()))

    response = client.post(
        "/api/auth/login",
        json={"username": "u", "password": "p", "sid": "237791864815616"},
    )
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "auth_error", "message": "session expired", "retryable": False}
    }

    response = client.get("/api/activities")
    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True

    response = client.post(
        "/api/signup/plans",
        json={
            "activity_id": "ACT-1001",
            "activity_title": "合成活动",
            "run_at": "2026-06-08T18:30:00+00:00",
        },
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_error"

    response = client.delete("/api/signup/plans/404")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_web_framework_errors_return_unified_json_without_detail():
    client = TestClient(create_app(MockService()))

    response = client.post("/api/auth/login", json={"username": "u"})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "detail" not in data
    assert data["error"]["code"] == "validation_error"
    assert data["error"]["retryable"] is False

    response = client.get("/api/not-found")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "detail" not in data
    assert data["error"]["code"] == "not_found"

    response = client.post("/api/activities")
    assert response.status_code == 405
    data = response.json()
    assert "error" in data
    assert "detail" not in data
    assert data["error"]["code"] == "method_not_allowed"


def test_web_error_handler_maps_risk_and_business_errors():
    class ErrorService(MockService):
        async def login(self, username, password, school_sid):
            raise RiskControlError("captcha")

        async def activity_detail(self, activity_id, refresh=False):
            raise BusinessError("bad activity")

    client = TestClient(create_app(ErrorService()))

    response = client.post(
        "/api/auth/login",
        json={"username": "u", "password": "p", "sid": "237791864815616"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "risk_control_error"

    response = client.get("/api/activities/ACT-1001")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "business_error"


def test_web_reminders_endpoint_whitelists_fields_and_serializes_datetime():
    class ReminderService(MockService):
        async def reminders(self):
            return [
                Activity(
                    activity_id="A",
                    title="T",
                    start_time=datetime(2026, 1, 1, tzinfo=UTC),
                    raw={"secret": "x"},
                )
            ]

    response = TestClient(create_app(ReminderService())).get("/api/reminders")
    assert set(response.json()[0]) == {
        "activity_id",
        "title",
        "activity_type",
        "location",
        "start_time",
        "end_time",
        "organizer",
        "status",
    }
    assert response.json()[0]["start_time"].endswith("Z")
    assert "secret" not in response.text


def test_reminders_page_script_isolated_from_normal_pages():
    client = TestClient(create_app(MockService()))
    reminder, normal = client.get("/reminders").text, client.get("/").text
    assert '/static/reminders.js' in reminder and '/static/app.js' not in reminder
    assert '/static/app.js' in normal and '/static/reminders.js' not in normal
