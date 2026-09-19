from __future__ import annotations

import asyncio
from datetime import datetime

from pu_mcp.activity_parser import (
    SIGNED_IN_FIELDS,
    STATUS_FIELDS,
    apply_eligibility,
    is_detail_shaped,
    is_list_shaped_unknown,
    parse_activity_detail,
    parse_activity_list,
)
from pu_mcp.config import Settings
from pu_mcp.errors import PuToolError
from pu_mcp.models import Activity, AuthSession, SignupAttempt, SignupPlan
from pu_mcp.pu_client import PuClient
from pu_mcp.security import KeyringSessionStore, SessionStore, mask_secret
from pu_mcp.storage import Storage
from pu_mcp.time_utils import ensure_aware_local

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
ENRICH_CONCURRENCY = 6
# Cap optional-only activity/info HTTP fills (content/location/human status).
# Type/sign-in enrichment is uncapped (already required for erke accuracy).
ENRICH_OPTIONAL_HTTP_LIMIT = 8


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

    def _session_year_college(self) -> tuple[str | None, str | None]:
        session = self.session_store.load() or getattr(self.client, "session", None)
        if session is None:
            return None, None
        return getattr(session, "year", None), getattr(session, "college", None)

    def _apply_session_eligibility(self, activity: Activity) -> Activity:
        year, college = self._session_year_college()
        return apply_eligibility(activity, user_year=year, user_college=college)

    def _apply_session_eligibility_many(self, activities: list[Activity]) -> list[Activity]:
        year, college = self._session_year_college()
        return [
            apply_eligibility(activity, user_year=year, user_college=college)
            for activity in activities
        ]

    async def login(self, username: str, password: str, school_sid: str) -> AuthSession:
        session = await self.client.login(username, password, school_sid)
        self.session_store.save(session)
        self.storage.clear_activity_caches()
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
        self.storage.clear_activity_caches()

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
        use_list_cache = _is_canonical_list_filters(filters)
        if not refresh and use_list_cache:
            cached = self.storage.get_cached_activity_list(max_age_seconds=ttl)
            if cached:
                enriched = await self._enrich_activities(cached, resolve_sign_in=False)
                if enriched != cached:
                    self.storage.cache_activity_list(enriched)
                return self._apply_session_eligibility_many(
                    self._filter_cached_activities(enriched, filters)
                )
        activities = parse_activity_list(
            await self.client.activity_list(**_server_list_filters(filters))
        )
        activities = await self._enrich_activities(activities, resolve_sign_in=False)
        if use_list_cache:
            self.storage.cache_activity_list(activities)
        return self._apply_session_eligibility_many(
            self._filter_cached_activities(activities, filters)
        )

    async def activity_detail(self, activity_id: str, *, refresh: bool = False) -> Activity:
        ttl = self.settings.activity_cache_ttl_seconds
        cached = self.storage.get_cached_activity(activity_id, max_age_seconds=ttl)
        list_source = _list_cache_sibling(self.storage, activity_id, ttl)
        if not refresh and cached is not None and not is_list_shaped_unknown(cached):
            merged = _preserve_signup_from_list(cached, list_source)
            if merged != cached:
                self.storage.cache_activity(merged)
            return self._apply_session_eligibility(merged)
        activity = parse_activity_detail(
            await self.client.activity_info(activity_id), activity_id=activity_id
        )
        merged = _preserve_signup_from_list(activity, list_source)
        if not merged.signup_status:
            merged = _preserve_signup_from_list(merged, cached)
        self.storage.cache_activity(merged)
        return self._apply_session_eligibility(merged)

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
        return self._apply_session_eligibility_many(
            await self._enrich_activities(merged, resolve_sign_in=True)
        )

    async def join_activity(self, activity_id: str) -> dict:
        return await self.client.join_activity(activity_id)

    async def cancel_activity(self, activity_id: str) -> dict:
        return await self.client.cancel_activity(activity_id)

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

    async def _enrich_activities(
        self, activities: list[Activity], *, resolve_sign_in: bool
    ) -> list[Activity]:
        semaphore = asyncio.Semaphore(ENRICH_CONCURRENCY)
        optional_http_remaining = ENRICH_OPTIONAL_HTTP_LIMIT
        optional_http_lock = asyncio.Lock()

        def _merge_from_detail(
            activity: Activity, detail: Activity, *, sign_resolved: bool
        ) -> Activity:
            needs_type = activity.activity_type == "未知"
            needs_content = not activity.content
            needs_location = not activity.location
            needs_status = not activity.status
            needs_status_code = not activity.status_code
            updates: dict[str, object] = {}
            # Copy signed_in only when the list payload has no sign-in flag.
            if not sign_resolved:
                updates["signed_in"] = detail.signed_in
            if needs_type and detail.activity_type != "未知":
                updates["activity_type"] = detail.activity_type
            if needs_content and detail.content:
                updates["content"] = detail.content
            if needs_location and detail.location:
                updates["location"] = detail.location
            if needs_status and detail.status:
                updates["status"] = detail.status
            if needs_status_code and detail.status_code:
                updates["status_code"] = detail.status_code
            if not activity.signup_status and detail.signup_status:
                updates["signup_status"] = detail.signup_status
                updates["allow_signup"] = detail.allow_signup
            # Participation rules come from activity/info; never clobber list signup window.
            if detail.allowed_years or detail.allowed_colleges or is_detail_shaped(detail):
                updates["allowed_years"] = detail.allowed_years
                updates["allowed_colleges"] = detail.allowed_colleges
            if activity.signup_start_time is None and detail.signup_start_time is not None:
                updates["signup_start_time"] = detail.signup_start_time
            if activity.signup_end_time is None and detail.signup_end_time is not None:
                updates["signup_end_time"] = detail.signup_end_time
            if not updates:
                return activity
            return activity.model_copy(update=updates)

        async def enrich_one(activity: Activity) -> Activity:
            if not activity.activity_id:
                return activity
            sign_resolved = _sign_in_resolved(activity)
            needs_type = activity.activity_type == "未知"
            needs_sign = resolve_sign_in and not sign_resolved
            needs_content = not activity.content
            needs_location = not activity.location
            needs_status = not activity.status
            # List usually has startTimeValue → signup_status; only then skip.
            # Do NOT treat missing signup_end_time alone as optional
            # (live list often omits joinEndTime).
            needs_signup = not activity.signup_status
            # status_code alone must not force HTTP; fill from TTL-aware cache only.
            needs_optional = needs_content or needs_location or needs_status or needs_signup
            needs_status_code = not activity.status_code
            if not needs_type and not needs_sign and not needs_optional and not needs_status_code:
                return activity

            ttl = self.settings.activity_cache_ttl_seconds
            detail: Activity | None = None
            if needs_type or needs_sign:
                try:
                    async with semaphore:
                        detail = await self.activity_detail(activity.activity_id, refresh=False)
                except PuToolError:
                    return activity
            elif needs_optional:
                cached = self.storage.get_cached_activity(activity.activity_id, max_age_seconds=ttl)
                if cached is not None and not is_list_shaped_unknown(cached):
                    detail = cached
                else:
                    async with optional_http_lock:
                        nonlocal optional_http_remaining
                        if optional_http_remaining <= 0:
                            return activity
                        optional_http_remaining -= 1
                    try:
                        async with semaphore:
                            detail = await self.activity_detail(activity.activity_id, refresh=False)
                    except PuToolError:
                        return activity
            else:
                cached = self.storage.get_cached_activity(activity.activity_id, max_age_seconds=ttl)
                if cached is None or is_list_shaped_unknown(cached):
                    return activity
                detail = cached
            return _merge_from_detail(activity, detail, sign_resolved=sign_resolved)

        return list(await asyncio.gather(*[enrich_one(activity) for activity in activities]))

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


def _my_list_has_more_pages(*, data: object, item_count: int, page: int, limit: int) -> bool:
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


def _server_list_filters(filters: dict[str, object]) -> dict[str, object]:
    """PU activity_list only accepts pagination; keyword/activity_type are local."""
    return {key: filters[key] for key in ("page", "limit") if key in filters}


def _preserve_signup_from_list(activity: Activity, source: Activity | None) -> Activity:
    # List startTimeValue/buttonInfo signup wins; keep detail join-window times.
    if source is None or not source.signup_status:
        return activity
    if (
        activity.signup_status == source.signup_status
        and activity.allow_signup == source.allow_signup
    ):
        return activity
    return activity.model_copy(
        update={
            "signup_status": source.signup_status,
            "allow_signup": source.allow_signup,
        }
    )


def _list_cache_sibling(
    storage: Storage, activity_id: str, max_age_seconds: float | None
) -> Activity | None:
    for item in storage.get_cached_activity_list(max_age_seconds=max_age_seconds):
        if item.activity_id == activity_id:
            return item
    return None


def _is_canonical_list_filters(filters: dict[str, object]) -> bool:
    """First-page catalog cache; keyword and activity_type are local filters."""
    allowed = {"page", "limit", "keyword", "activity_type"}
    if any(key not in allowed for key in filters):
        return False
    try:
        page = int(filters.get("page") or 1)
        limit = int(filters.get("limit") or 20)
    except (TypeError, ValueError):
        return False
    return page == 1 and limit == 20


def _raw_has_signed_in_field(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    if any(field in raw for field in SIGNED_IN_FIELDS):
        return True
    for key in ("userStatus", "user_status"):
        nested = raw.get(key)
        if isinstance(nested, dict) and ("hasSignIn" in nested or "has_sign_in" in nested):
            return True
    return False


def _sign_in_resolved(activity: Activity) -> bool:
    raw = activity.raw if isinstance(activity.raw, dict) else {}
    if _raw_has_signed_in_field(raw):
        return True
    for field in STATUS_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and "已签到" in value:
            return True
    return False


def build_service() -> PuService:
    return PuService()
