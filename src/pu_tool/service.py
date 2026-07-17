from __future__ import annotations

from datetime import datetime

from pu_tool.activity_parser import parse_activity_detail, parse_activity_list
from pu_tool.config import Settings
from pu_tool.errors import AuthError, RiskControlError
from pu_tool.models import Activity, AuthSession, SignupAttempt, SignupPlan
from pu_tool.pu_client import PuClient
from pu_tool.security import KeyringSessionStore, SessionStore, mask_secret
from pu_tool.storage import Storage
from pu_tool.time_utils import ensure_aware_local

REMINDER_DETAIL_FIELDS = (
    "title",
    "activity_type",
    "location",
    "start_time",
    "end_time",
    "organizer",
    "status",
)


def _missing_reminder_field(activity: Activity, key: str) -> bool:
    value = getattr(activity, key, None)
    return value in (None, "") or (
        key == "activity_type"
        and value == Activity.model_fields["activity_type"].default
    )


class PuService:
    def __init__(
        self,
        client: PuClient | None = None,
        storage: Storage | None = None,
        session_store: SessionStore | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or Settings()
        self.session_store = session_store or KeyringSessionStore()
        session = self.session_store.load()
        self.client = client or PuClient(
            base_url=self.settings.base_url,
            session=session,
            timeout_seconds=self.settings.request_timeout_seconds,
            min_interval_seconds=self.settings.min_request_interval_seconds,
            max_retries=self.settings.max_retries,
        )
        self.storage = storage or Storage(self.settings.db_path)

    async def login(self, username: str, password: str, school_sid: str) -> AuthSession:
        session = await self.client.login(username, password, school_sid)
        self.session_store.save(session)
        return session

    def auth_status(self) -> dict[str, object]:
        session = self.session_store.load() or getattr(self.client, "session", None)
        if not session:
            return {"authenticated": False, "message": "仅用于本人账号，本地低频使用。"}
        return {
            "authenticated": True,
            "user": session.masked_user,
            "token": mask_secret(session.token),
            "sid": mask_secret(session.sid),
            "message": "仅用于本人账号，本地低频使用。",
        }

    def logout(self) -> None:
        self.session_store.clear()
        if hasattr(self.client, "session"):
            self.client.session = None

    async def list_activities(
        self,
        *,
        refresh: bool = False,
        cache_ttl_seconds: float | None = None,
        **filters: object,
    ) -> list[Activity]:
        filters = {"page": 1, "limit": 20, **filters}
        ttl = (
            self.settings.activity_cache_ttl_seconds
            if cache_ttl_seconds is None
            else cache_ttl_seconds
        )
        if not refresh:
            cached = self.storage.list_cached_activities(max_age_seconds=ttl)
            if cached:
                return self._filter_cached_activities(cached, filters)
        activities = parse_activity_list(await self.client.activity_list(**filters))
        for activity in activities:
            self.storage.cache_activity(activity)
        return activities

    async def activity_detail(self, activity_id: str, *, refresh: bool = False) -> Activity:
        if not refresh:
            cached = self.storage.get_cached_activity(
                activity_id,
                max_age_seconds=self.settings.activity_cache_ttl_seconds,
            )
            if cached is not None:
                return cached
        activity = parse_activity_detail(await self.client.activity_info(activity_id))
        self.storage.cache_activity(activity)
        return activity

    async def joined_activities(self) -> list[Activity]:
        return parse_activity_list(await self.client.my_list())

    async def reminders(self) -> list[Activity]:
        joined = await self.joined_activities()
        result: list[Activity] = []
        for activity in joined:
            if any(
                _missing_reminder_field(activity, key)
                for key in REMINDER_DETAIL_FIELDS
            ):
                try:
                    detail = await self.activity_detail(activity.activity_id, refresh=False)
                    data = activity.model_dump()
                    for key in REMINDER_DETAIL_FIELDS:
                        if _missing_reminder_field(activity, key) and getattr(
                            detail, key, None
                        ):
                            data[key] = getattr(detail, key)
                    activity = Activity(**data)
                except (AuthError, RiskControlError):
                    raise
                except Exception:
                    pass
            result.append(activity)
        return result

    def create_signup_plan(
        self,
        activity_id: str,
        activity_title: str,
        run_at: datetime,
        max_attempts: int = 1,
    ) -> SignupPlan:
        plan = SignupPlan(
            activity_id=activity_id,
            activity_title=activity_title,
            run_at=ensure_aware_local(run_at),
            max_attempts=max_attempts,
        )
        return self.storage.create_plan(plan)

    def list_signup_plans(self) -> list[SignupPlan]:
        return self.storage.list_plans()

    def cancel_signup_plan(self, plan_id: int) -> SignupPlan:
        return self.storage.cancel_plan(plan_id)

    def list_signup_attempts(self, plan_id: int | None = None) -> list[SignupAttempt]:
        return self.storage.list_attempts(plan_id=plan_id)

    async def execute_signup_plan(self, plan_id: int) -> SignupAttempt:
        plan = self.storage.get_plan(plan_id)
        self.storage.update_plan_status(plan_id, "running")
        joined = await self.joined_activities()
        if any(activity.activity_id == plan.activity_id for activity in joined):
            return self.storage.record_attempt_status(plan, "skipped", "already joined")
        data = await self.client.join_activity(plan.activity_id)
        return self.storage.record_attempt_status(
            plan, "succeeded", str(data.get("msg", "报名成功"))
        )

    def _filter_cached_activities(
        self, activities: list[Activity], filters: dict[str, object]
    ) -> list[Activity]:
        keyword = str(filters.get("keyword") or "").strip().lower()
        activity_type = str(filters.get("activity_type") or "").strip()
        result = activities
        if keyword:
            result = [
                activity
                for activity in result
                if keyword in activity.activity_id.lower() or keyword in activity.title.lower()
            ]
        if activity_type:
            result = [
                activity for activity in result if activity.activity_type == activity_type
            ]
        return result


def build_service() -> PuService:
    return PuService()
