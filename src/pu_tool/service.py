from __future__ import annotations

from datetime import datetime

from pu_tool.activity_parser import parse_activity_detail, parse_activity_list
from pu_tool.config import Settings
from pu_tool.models import Activity, AuthSession, SignupAttempt, SignupPlan
from pu_tool.pu_client import PuClient
from pu_tool.security import KeyringSessionStore, SessionStore, mask_secret
from pu_tool.storage import Storage
from pu_tool.time_utils import ensure_aware_local

COUNTABLE_ACTIVITY_TYPES = (
    "社会实践",
    "校园文化",
    "思想引领",
    "学科竞赛",
    "学术讲座",
    "体育健身",
)
# myList request `type` tabs (1–3; 0 and ≥4 are invalid per live API), not 活动类型 labels.
JOINED_LIST_TYPES = (1, 2, 3)
MY_LIST_PAGE_LIMIT = 20
MY_LIST_MAX_PAGES = 50


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

    async def search_schools(self, keyword: str, limit: int = 20) -> list[dict[str, object]]:
        needle = str(keyword or "").strip()
        if not needle:
            raise ValueError("keyword must not be empty")
        lowered = needle.lower()
        matched: list[dict[str, object]] = []
        for item in await self.client.school_list():
            name = str(item.get("name") or "")
            short = str(item.get("short") or "")
            if lowered not in name.lower() and lowered not in short.lower():
                continue
            matched.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "short": item.get("short"),
                    "casUrl": item.get("casUrl"),
                }
            )
            if len(matched) >= limit:
                break
        return matched

    async def list_activities(
        self,
        *,
        refresh: bool = False,
        cache_ttl_seconds: float | None = None,
        **filters: object,
    ) -> list[Activity]:
        filters = {key: value for key, value in filters.items() if value is not None}
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
        merged: list[Activity] = []
        seen: set[str] = set()
        for list_type in JOINED_LIST_TYPES:
            page = 1
            while page <= MY_LIST_MAX_PAGES:
                payload = await self.client.my_list(
                    type=list_type, page=page, limit=MY_LIST_PAGE_LIMIT
                )
                activities = parse_activity_list(payload)
                for activity in activities:
                    if activity.activity_id in seen:
                        continue
                    seen.add(activity.activity_id)
                    merged.append(activity)
                data = payload.get("data") if isinstance(payload, dict) else None
                if not _my_list_has_more_pages(
                    data=data,
                    item_count=len(activities),
                    page=page,
                    limit=MY_LIST_PAGE_LIMIT,
                ):
                    break
                page += 1
        return merged

    async def join_activity(self, activity_id: str) -> dict:
        return await self.client.join_activity(activity_id)

    async def attendance_counts(self) -> dict[str, int]:
        counts = {name: 0 for name in COUNTABLE_ACTIVITY_TYPES}
        for activity in await self.joined_activities():
            if activity.signed_in and activity.activity_type in counts:
                counts[activity.activity_type] += 1
        return counts

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
            result = [activity for activity in result if activity.activity_type == activity_type]
        return result


def _page_info(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    info = data.get("pageInfo") or data.get("page_info") or {}
    return info if isinstance(info, dict) else {}


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _first_int(mapping: dict, *keys: str) -> int | None:
    for key in keys:
        parsed = _safe_int(mapping.get(key))
        if parsed is not None:
            return parsed
    return None


def _my_list_has_more_pages(
    *, data: object, item_count: int, page: int, limit: int
) -> bool:
    # Paginate via pageInfo. Empty/short pages always stop. A full page with
    # no usable pageInfo also stops so a missing total cannot loop forever.
    if item_count == 0 or item_count < limit:
        return False
    info = _page_info(data)
    total_page = _first_int(info, "totalPage", "total_page", "pages")
    if total_page is not None:
        return page < total_page
    total = _first_int(info, "total", "count")
    if total is not None:
        return page * limit < total
    return False


def build_service() -> PuService:
    return PuService()
