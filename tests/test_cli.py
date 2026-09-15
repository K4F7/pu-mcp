from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from typer.testing import CliRunner

from pu_mcp import cli
from pu_mcp.errors import BusinessError
from pu_mcp.models import Activity, AuthSession, ScoreItem

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
                location="虚构活动室 A",
                content="合成活动说明正文",
                status="进行中",
                status_code="5",
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

    async def activity_detail(self, activity_id, refresh=False):
        return (await self.list_activities())[0]

    async def joined_activities(self):
        return []

    def create_signup_plan(self, activity_id, activity_title, run_at, max_attempts=1):
        from pu_mcp.models import SignupPlan

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
        from pu_mcp.models import SignupPlan

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

    async def join_activity(self, activity_id):
        self.joined_id = activity_id
        return {"code": 0, "msg": "报名成功"}

    async def attendance_counts(self):
        return {
            "社会实践": 0,
            "校园文化": 1,
            "思想引领": 0,
            "学科竞赛": 0,
            "学术讲座": 0,
            "体育健身": 0,
        }

    async def search_schools(self, keyword, limit=20):
        if not str(keyword or "").strip():
            raise ValueError("keyword must not be empty")
        self.search_keyword = keyword
        self.search_limit = limit
        return [
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


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_help_works():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "activities" in plain
    assert "mcp" in plain
    assert "schools" in plain
    assert "erke" in plain
    assert "signup" not in plain.lower()
    assert "serve" not in plain.lower()
    activities = runner.invoke(cli.app, ["activities", "--help"])
    assert activities.exit_code == 0
    assert "join" in _plain(activities.output)
    schools = runner.invoke(cli.app, ["schools", "--help"])
    assert schools.exit_code == 0
    assert "search" in _plain(schools.output)


def test_cli_schools_search_json_matches_mcp_shape(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["schools", "search", "南昌", "--json"])
    assert result.exit_code == 0
    assert '"schools"' in result.output
    assert '"id": "237791864815616"' in result.output
    assert '"name": "南昌大学"' in result.output
    assert '"short": "ncu"' in result.output
    assert '"casUrl": "https://cas.example.edu.cn/ncu"' in result.output
    assert '"id": "111222333444555"' in result.output
    assert '"name": "南昌航空大学"' in result.output


def test_cli_school_search_json_matches_mcp_shape(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["school", "search", "南昌", "--json"])
    assert result.exit_code == 0
    assert '"schools"' in result.output
    assert '"id": "237791864815616"' in result.output
    assert '"name": "南昌大学"' in result.output
    assert '"short": "ncu"' in result.output
    assert '"casUrl": "https://cas.example.edu.cn/ncu"' in result.output
    assert '"id": "111222333444555"' in result.output
    assert '"name": "南昌航空大学"' in result.output


def test_cli_school_search_rejects_empty_keyword(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["school", "search", "   ", "--json"])
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "empty" in result.output


def test_cli_activity_list_displays_type_and_scores(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["activities", "list"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "志愿公益" in plain
    assert "进行中" in plain
    assert "虚构活动室 A" in plain
    assert "合成活动说明" in plain  # human table may ellipsize long content
    json_result = runner.invoke(cli.app, ["activities", "list", "--json"])
    assert json_result.exit_code == 0
    payload = json.loads(_plain(json_result.output))
    assert payload[0]["content"] == "合成活动说明正文"
    assert payload[0]["location"] == "虚构活动室 A"
    assert payload[0]["score_items"]


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


def test_cli_login_rejects_chinese_school_name_as_sid(monkeypatch):
    captured = {}

    class CapturingService(MockService):
        async def login(self, username, password, school_sid):
            captured["called"] = True
            return AuthSession(token="tok", sid="sid", masked_user=username)

    monkeypatch.setattr(cli, "build_service", lambda: CapturingService())
    result = runner.invoke(
        cli.app,
        [
            "login",
            "--username",
            "fake-number",
            "--sid",
            "南昌大学",
            "--password",
            "fake-password",
        ],
    )
    assert result.exit_code == 1
    assert captured == {}
    assert "Traceback" not in result.output
    assert "sid" in result.output.lower()
    assert "fake-password" not in result.output


def test_cli_login_help_has_no_school_name_argument():
    result = runner.invoke(cli.app, ["login", "--help"])
    assert result.exit_code == 0
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--sid" in plain
    assert "--encoded-sid" in plain
    assert "--school-name" not in plain
    assert "校名" not in plain


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


def test_cli_login_short_flags_succeed_with_empty_stdin(monkeypatch):
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
        ["login", "-u", "fake-user", "-p", "fake-password", "--sid", "237791864815616"],
        input="",
    )

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-user",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "fake-password" not in result.output


def test_cli_login_reads_password_from_pu_password_env(monkeypatch):
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
    monkeypatch.setenv("PU_PASSWORD", "fake-password")

    result = runner.invoke(
        cli.app,
        ["login", "-u", "fake-user", "--sid", "237791864815616"],
        input="",
    )

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-user",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "fake-password" not in result.output


def test_cli_login_reads_sid_from_pu_sid_env(monkeypatch):
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
    monkeypatch.setenv("PU_SID", "237791864815616")

    result = runner.invoke(
        cli.app,
        ["login", "-u", "fake-user", "-p", "fake-password"],
        input="",
    )

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-user",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "fake-password" not in result.output


def test_cli_login_three_env_fields_noninteractive(monkeypatch):
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
    monkeypatch.setenv("PU_USERNAME", "fake-user")
    monkeypatch.setenv("PU_PASSWORD", "fake-password")
    monkeypatch.setenv("PU_SID", "237791864815616")

    result = runner.invoke(cli.app, ["login"], input="")

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-user",
        "password": "fake-password",
        "school_sid": "237791864815616",
    }
    assert "fake-password" not in result.output


def test_cli_login_cli_sid_overrides_pu_sid_env(monkeypatch):
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
    monkeypatch.setenv("PU_SID", "237791864815616")

    result = runner.invoke(
        cli.app,
        [
            "login",
            "-u",
            "fake-user",
            "-p",
            "fake-password",
            "--sid",
            "111111111111111",
        ],
        input="",
    )

    assert result.exit_code == 0
    assert captured == {
        "username": "fake-user",
        "password": "fake-password",
        "school_sid": "111111111111111",
    }
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
    monkeypatch.delenv("PU_SID", raising=False)

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


def test_cli_activities_join_calls_service(monkeypatch):
    service = MockService()
    monkeypatch.setattr(cli, "build_service", lambda: service)
    result = runner.invoke(cli.app, ["activities", "join", "ACT-1001"])
    assert result.exit_code == 0
    assert service.joined_id == "ACT-1001"
    assert '"msg": "报名成功"' in result.output


def test_cli_activities_join_prints_business_error_without_traceback(monkeypatch):
    class FailingService(MockService):
        async def join_activity(self, activity_id):
            raise BusinessError("已报名该活动")

    monkeypatch.setattr(cli, "build_service", lambda: FailingService())
    result = runner.invoke(cli.app, ["activities", "join", "ACT-1001"])
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "已报名该活动" in result.output


def test_cli_erke_prints_attendance_counts_only(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["erke"])
    assert result.exit_code == 0
    payload = json.loads(_plain(result.output))
    assert payload == {
        "counts": {
            "社会实践": 0,
            "校园文化": 1,
            "思想引领": 0,
            "学科竞赛": 0,
            "学术讲座": 0,
            "体育健身": 0,
        }
    }
    assert "已获" not in result.output
    assert "必须补" not in result.output
    assert "总有效分" not in result.output
    assert "阶段线" not in result.output


def test_cli_signup_product_is_removed():
    help_result = runner.invoke(cli.app, ["--help"])
    assert help_result.exit_code == 0
    plain = _plain(help_result.output).lower()
    assert "signup" not in plain
    assert "serve" not in plain
    result = runner.invoke(cli.app, ["signup", "--help"])
    assert result.exit_code != 0
    serve_result = runner.invoke(cli.app, ["serve", "--help"])
    assert serve_result.exit_code != 0


def test_cli_activities_joined_marks_signed_in(monkeypatch):
    class MixedJoinedService(MockService):
        async def joined_activities(self):
            return [
                Activity(
                    activity_id="ACT-2001",
                    title="校园文化讲座",
                    activity_type="校园文化",
                    location="虚构报告厅",
                    content="讲座正文预览",
                    status="进行中",
                    status_code="5",
                    signed_in=True,
                ),
                Activity(
                    activity_id="ACT-2002",
                    title="社会实践调研",
                    activity_type="社会实践",
                    location="虚构活动室 B",
                    content="调研正文预览",
                    status="未开始",
                    status_code="21",
                    signed_in=False,
                ),
            ]

    monkeypatch.setattr(cli, "build_service", lambda: MixedJoinedService())
    result = runner.invoke(cli.app, ["activities", "joined"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    signed_line = next(line for line in plain.splitlines() if "ACT-2001" in line)
    unsigned_line = next(line for line in plain.splitlines() if "ACT-2002" in line)
    assert "已签到" in signed_line
    assert "未签到" not in signed_line
    assert "进行中" in signed_line
    assert "虚构报告厅" in signed_line
    assert "讲座正文" in signed_line  # human table may ellipsize
    assert "未签到" in unsigned_line
    assert "未开始" in unsigned_line
    assert "虚构活动" in unsigned_line  # human table may ellipsize

    json_result = runner.invoke(cli.app, ["activities", "joined", "--json"])
    assert json_result.exit_code == 0
    payload = json.loads(_plain(json_result.output))
    assert payload[0]["signed_in"] is True
    assert payload[1]["signed_in"] is False
    assert payload[0]["status"] == "进行中"
    assert payload[0]["status_code"] == "5"
    assert payload[0]["location"] == "虚构报告厅"
    assert payload[0]["content"] == "讲座正文预览"
    assert payload[1]["location"] == "虚构活动室 B"
    assert payload[1]["content"] == "调研正文预览"


def test_cli_activities_info_prints_content_and_human_status(monkeypatch):
    monkeypatch.setattr(cli, "build_service", lambda: MockService())
    result = runner.invoke(cli.app, ["activities", "info", "ACT-1001"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "内容：合成活动说明正文" in plain
    assert "状态：进行中" in plain
    assert "5" not in plain.split("状态：", 1)[1].splitlines()[0]

    json_result = runner.invoke(cli.app, ["activities", "info", "ACT-1001", "--json"])
    assert json_result.exit_code == 0
    payload = json.loads(_plain(json_result.output))
    assert payload["content"] == "合成活动说明正文"
    assert payload["status"] == "进行中"
    assert payload["status_code"] == "5"
