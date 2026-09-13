from __future__ import annotations

from datetime import UTC, datetime

from typer.testing import CliRunner

from pu_tool import cli
from pu_tool.errors import BusinessError
from pu_tool.models import Activity, AuthSession, ScoreItem

runner = CliRunner()


class MockService:
    def __init__(self):
        self.list_filters = None

    def auth_status(self):
        return {"authenticated": True, "token": "test...3456", "sid": "test...4321", "user": "demo"}

    async def login(self, username, password, school_sid):
        return AuthSession(
            token="test-token-abcdef123456", sid="test-sid-654321", masked_user=username
        )

    async def list_activities(self, **filters):
        self.list_filters = filters
        return [
            Activity(
                activity_id="ACT-1001",
                title="合成志愿服务活动",
                activity_type="志愿公益",
                score_items=[
                    ScoreItem(
                        kind="credit", label="加分", value="2", unit="分", source_field="score"
                    ),
                    ScoreItem(
                        kind="academic_credit",
                        label="学分",
                        value="0.5",
                        unit="学分",
                        source_field="credit",
                    ),
                ],
            )
        ]

    async def activity_detail(self, activity_id):
        return (await self.list_activities())[0]

    async def joined_activities(self):
        return []

    def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
        from pu_tool.models import SignupPlan

        return SignupPlan(
            plan_id=1,
            activity_id=activity_id,
            activity_title=activity_title,
            run_at=run_at,
            max_attempts=max_attempts,
        )

    def list_signup_plans(self):
        return []

    def cancel_signup_plan(self, plan_id):
        from pu_tool.models import SignupPlan

        return SignupPlan(
            plan_id=plan_id,
            activity_id="ACT-1001",
            activity_title="合成活动",
            run_at=datetime.now(UTC),
            enabled=False,
            status="cancelled",
        )

    def list_signup_attempts(self, plan_id=None):
        return []

    async def execute_signup_plan(self, plan_id):
        from pu_tool.models import SignupAttempt

        return SignupAttempt(
            attempt_id=1,
            plan_id=plan_id,
            activity_id="ACT-1001",
            status="succeeded",
            message="报名成功",
        )


def test_cli_help_works():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "activities" in result.output


def test_cli_activity_list_displays_type_and_scores(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["activities", "list"])
    assert result.exit_code == 0
    assert "志愿公益" in result.output
    assert "加分:2分" in result.output


def test_cli_json_output(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["activities", "list", "--json"])
    assert result.exit_code == 0
    assert '"activity_id": "ACT-1001"' in result.output


def test_cli_activity_list_defaults_to_page_one(monkeypatch):
    service = MockService()
    monkeypatch.setattr(cli, "build_service", lambda: service)
    result = runner.invoke(cli.app, ["activities", "list", "--json"])
    assert result.exit_code == 0
    assert service.list_filters["page"] == 1


def test_cli_activity_list_defaults_to_limit_twenty(monkeypatch):
    service = MockService()
    monkeypatch.setattr(cli, "build_service", lambda: service)
    result = runner.invoke(cli.app, ["activities", "list", "--json"])
    assert result.exit_code == 0
    assert service.list_filters["limit"] == 20


def test_cli_activity_list_accepts_page(monkeypatch):
    service = MockService()
    monkeypatch.setattr(cli, "build_service", lambda: service)
    result = runner.invoke(cli.app, ["activities", "list", "--page", "2", "--json"])
    assert result.exit_code == 0
    assert service.list_filters["page"] == 2


def test_cli_activity_list_accepts_limit(monkeypatch):
    service = MockService()
    monkeypatch.setattr(cli, "build_service", lambda: service)
    result = runner.invoke(cli.app, ["activities", "list", "--limit", "5", "--json"])
    assert result.exit_code == 0
    assert service.list_filters["limit"] == 5


def test_cli_auth_status_masks_secret(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["auth", "status"])
    assert result.exit_code == 0
    assert "abcdef123456" not in result.output


def test_cli_login_uses_numeric_school_sid_without_printing_password(monkeypatch):
    captured = {}

    class CapturingService(MockService):
        async def login(self, username, password, school_sid):
            captured["username"] = username
            captured["password"] = password
            captured["school_sid"] = school_sid
            return AuthSession(
                token="test-token-abcdef123456",
                sid="auth-sid-from-response",
                masked_user=username,
            )

    monkeypatch.setattr(cli, "build_service", lambda: CapturingService())

    result = runner.invoke(
        cli.app,
        [
            "login",
            "--username",
            "fake-number",
            "--sid",
            "237791864815616",
            "--password",
            "fake-password",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-number",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "auth-sid-from-response" not in result.output
    assert "fake-password" not in result.output


def test_cli_login_decodes_encoded_sid_from_class_url_without_printing_password(monkeypatch):
    captured = {}

    class CapturingService(MockService):
        async def login(self, username, password, school_sid):
            captured["username"] = username
            captured["password"] = password
            captured["school_sid"] = school_sid
            return AuthSession(
                token="test-token-abcdef123456",
                sid="auth-sid-from-response",
                masked_user=username,
            )

    monkeypatch.setattr(cli, "build_service", lambda: CapturingService())

    result = runner.invoke(
        cli.app,
        [
            "login",
            "--username",
            "fake-number",
            "--encoded-sid",
            "QVpTRFBVS19QS1hRRVhS",
            "--password",
            "fake-password",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-number",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "fake-password" not in result.output


def test_cli_signup_schedule_points_to_signup_run(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(
        cli.app,
        [
            "signup",
            "schedule",
            "ACT-1001",
            "--at",
            "2026-06-08T18:30:00+00:00",
        ],
    )
    assert result.exit_code == 0
    assert "pu signup run 1" in result.output.replace("\n", " ")
    assert "pu serve" not in result.output


def test_cli_signup_run_prints_attempt_json(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["signup", "run", "1"])
    assert result.exit_code == 0
    assert '"status": "succeeded"' in result.output
    assert "报名成功" in result.output


def test_cli_signup_schedule_normalizes_naive_at_to_local_aware(monkeypatch):
    captured = {}

    class CapturingService(MockService):
        def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
            captured["run_at"] = run_at
            return super().create_signup_plan(activity_id, activity_title, run_at, max_attempts)

    monkeypatch.setattr(cli, "build_service", lambda: CapturingService())
    result = runner.invoke(
        cli.app,
        [
            "signup",
            "schedule",
            "ACT-1001",
            "--at",
            "2026-06-08 18:30:00",
        ],
    )

    assert result.exit_code == 0
    assert captured["run_at"].tzinfo is not None
    assert captured["run_at"].utcoffset() is not None
    assert '"run_at": "2026-06-08T18:30:00' in result.output
    assert "+00:00" in result.output or "+" in result.output or "-" in result.output


def test_cli_signup_commands_handle_errors_without_traceback(monkeypatch):
    class ErrorService(MockService):
        def cancel_signup_plan(self, plan_id):
            raise KeyError(f"signup plan not found: {plan_id}")

        def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
            raise BusinessError("not allowed")

    monkeypatch.setattr(cli, "build_service", lambda: ErrorService())

    result = runner.invoke(cli.app, ["signup", "cancel", "404"])
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "signup plan not found" in result.output

    result = runner.invoke(
        cli.app,
        [
            "signup",
            "schedule",
            "ACT-1001",
            "--at",
            "2026-06-08T18:30:00+00:00",
        ],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "not allowed" in result.output
