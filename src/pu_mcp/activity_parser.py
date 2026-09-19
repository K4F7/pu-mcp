from __future__ import annotations

from datetime import datetime
from typing import Any

from pu_mcp.errors import ParseError
from pu_mcp.models import Activity, ScoreItem
from pu_mcp.time_utils import ensure_aware_local

TYPE_FIELDS = (
    "categoryName",
    "category_name",
    "typeName",
    "type_name",
    "category",
    "activityType",
    "activity_type",
)
ID_FIELDS = ("id", "activityId", "activity_id")
TITLE_FIELDS = ("title", "name", "activityName")
START_FIELDS = ("startTime", "start_time", "beginTime")
END_FIELDS = ("endTime", "end_time", "finishTime")
SIGNUP_START_FIELDS = ("joinStartTime", "applyStartTime", "signup_start", "signupStartTime")
SIGNUP_END_FIELDS = ("joinEndTime", "applyEndTime", "signup_end", "signupEndTime")
SIGNUP_STATUS_KNOWN = ("报名进行中", "报名已结束", "报名未开始")
LOCATION_FIELDS = ("address", "location", "place")
ORGANIZER_FIELDS = ("organizer", "host", "clubName")
STATUS_FIELDS = ("status", "state")
STATUS_CODE_FIELDS = STATUS_FIELDS
STATUS_NAME_FIELDS = ("statusName", "status_name")
STATUS_CODE_LABELS = {
    "5": "已结束",
    "21": "未开始",
    "22": "进行中",
    "23": "已结束",
}
CONTENT_FIELDS = ("description", "content")
SIGNED_IN_FIELDS = (
    "signedIn",
    "signed_in",
    "isSign",
    "is_sign",
    "hasSign",
    "has_sign",
    "hasSignIn",
    "has_sign_in",
    "signStatus",
    "sign_status",
    "signIn",
    "sign_in",
)
SIGNED_IN_TRUE = {True, "1", "true", "True", "yes", "YES", "已签到"}
SIGNED_IN_FALSE = {False, "0", "false", "False", "no", "NO", "未签到"}

SCORE_FIELDS: dict[str, tuple[str, str, str]] = {
    "score": ("credit", "加分", "分"),
    "bonusScore": ("credit", "加分", "分"),
    "bonus_score": ("credit", "加分", "分"),
    "credit": ("academic_credit", "学分", "学分"),
    "academicCredit": ("academic_credit", "学分", "学分"),
    "academic_credit": ("academic_credit", "学分", "学分"),
    "point": ("point", "积分", "分"),
    "points": ("point", "积分", "分"),
    "integral": ("point", "积分", "分"),
}


def _data(response: dict[str, Any]) -> Any:
    if not isinstance(response, dict):
        raise ParseError("response is not an object")
    return response.get("data", response)


def _first(raw: dict[str, Any], fields: tuple[str, ...], default: Any = None) -> Any:
    for field in fields:
        value = raw.get(field)
        if value not in (None, ""):
            return value
    return default


def _flatten_nested_activity_fields(raw: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(raw)
    for key in ("baseInfo", "base_info"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            flattened.update(nested)
            break
    for key in ("userStatus", "user_status"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            flattened.update(nested)
            break
    outer_id = raw.get("id")
    if outer_id not in (None, ""):
        flattened["id"] = outer_id
    return flattened


def _is_signed_in_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _score_items(raw: dict[str, Any]) -> list[ScoreItem]:
    items: list[ScoreItem] = []
    for field, (kind, label, unit) in SCORE_FIELDS.items():
        value = raw.get(field)
        if value in (None, ""):
            continue
        items.append(
            ScoreItem(
                kind=kind,
                label=label,
                value=str(value),
                unit=unit,
                source_field=field,
                raw=value,
            )
        )
    for field, value in raw.items():
        if field in SCORE_FIELDS or value in (None, ""):
            continue
        if "reward" in field.lower() or "奖励" in field:
            items.append(
                ScoreItem(
                    kind="unknown",
                    label="未识别奖励字段",
                    value=str(value),
                    source_field=field,
                    raw=value,
                )
            )
    return items


def _iter_button_info(raw: dict[str, Any]) -> list[dict[str, Any]]:
    value = raw.get("buttonInfo")
    if value is None:
        value = raw.get("button_info")
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _human_start_time_value(value: Any) -> str | None:
    if value in (None, "") or isinstance(value, bool | int | float):
        return None
    text = str(value).strip()
    if not text:
        return None
    if "报名" in text or text in SIGNUP_STATUS_KNOWN:
        return text
    return None


def _signup_status_from_window(
    start: datetime | None, end: datetime | None, now: datetime
) -> str | None:
    if start is None and end is None:
        return None
    current = ensure_aware_local(now)
    start_at = ensure_aware_local(start) if start is not None else None
    end_at = ensure_aware_local(end) if end is not None else None
    if start_at is not None and current < start_at:
        return "报名未开始"
    if end_at is not None and current > end_at:
        return "报名已结束"
    return "报名进行中"


def _parse_signup_state(
    raw: dict[str, Any],
    *,
    signup_start: datetime | None,
    signup_end: datetime | None,
    now: datetime | None,
) -> tuple[str | None, bool]:
    buttons = _iter_button_info(raw)
    has_join_event = any(item.get("event") == "join" for item in buttons)
    current = now if now is not None else datetime.now()
    signup_status = _human_start_time_value(raw.get("startTimeValue", raw.get("start_time_value")))
    if signup_status is None:
        if has_join_event:
            signup_status = "报名进行中"
        else:
            not_started = any("报名未开始" in str(item.get("name") or "") for item in buttons)
            unnamed = any(str(item.get("name") or "") == "未报名" for item in buttons)
            if not_started:
                signup_status = "报名未开始"
            elif unnamed:
                signup_status = (
                    _signup_status_from_window(signup_start, signup_end, current) or "报名已结束"
                )
            else:
                signup_status = _signup_status_from_window(signup_start, signup_end, current)
    allow_signup = signup_status == "报名进行中" or has_join_event
    return signup_status, allow_signup


def _parse_signed_in(raw: dict[str, Any]) -> bool:
    for field in SIGNED_IN_FIELDS:
        if field not in raw:
            continue
        value = raw[field]
        if _is_signed_in_int(value, 1) or value is True or value in SIGNED_IN_TRUE:
            return True
        if isinstance(value, str) and "已签到" in value:
            return True
        if _is_signed_in_int(value, 0) or value is False or value in SIGNED_IN_FALSE:
            return False
    for field in STATUS_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and "已签到" in value:
            return True
    return False


_DETAIL_NESTED_KEYS = ("baseInfo", "base_info", "userStatus", "user_status")
_DETAIL_TYPE_KEYS = ("categoryName", "category_name")


def is_detail_shaped(activity: Activity) -> bool:
    raw = activity.raw if isinstance(activity.raw, dict) else {}
    for key in _DETAIL_NESTED_KEYS:
        nested = raw.get(key)
        if isinstance(nested, dict) and nested:
            return True
    for key in _DETAIL_TYPE_KEYS:
        if raw.get(key) not in (None, ""):
            return True
    return False


def is_list_shaped_unknown(activity: Activity) -> bool:
    return activity.activity_type == "未知" and not is_detail_shaped(activity)


_PARTICIPATION_RULE_KEYS = ("allowYear", "allow_year", "allowCollege", "allow_college")


def participation_rules_known_in_raw(raw: dict[str, Any]) -> bool:
    return any(key in raw for key in _PARTICIPATION_RULE_KEYS)


def _allow_name_list(raw: dict[str, Any], *keys: str) -> list[str]:
    value = None
    for key in keys:
        if key in raw:
            value = raw.get(key)
            break
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
            if name not in (None, ""):
                names.append(str(name))
        elif item not in (None, ""):
            names.append(str(item))
    return names


def evaluate_eligibility(
    allowed_years: list[str],
    allowed_colleges: list[str],
    *,
    user_year: str | None = None,
    user_college: str | None = None,
) -> tuple[bool | None, str | None]:
    """Return (eligible, ineligible_reason).

    Empty restriction lists mean unrestricted. Missing user fields needed for a
    non-empty restriction yield eligible=None unless another restriction already
    proves the user ineligible.
    """
    reasons: list[str] = []
    incomplete = False
    if allowed_years:
        if user_year in (None, ""):
            incomplete = True
        elif str(user_year) not in allowed_years:
            reasons.append("年级不符合参与条件")
    if allowed_colleges:
        if user_college in (None, ""):
            incomplete = True
        elif str(user_college) not in allowed_colleges:
            reasons.append("学院不符合参与条件")
    if reasons:
        return False, "；".join(reasons)
    if incomplete:
        return None, None
    return True, None


def apply_eligibility(
    activity: Activity,
    *,
    user_year: str | None = None,
    user_college: str | None = None,
) -> Activity:
    """Recompute eligible/reason and gate allow_signup.

    ``activity.allow_signup`` must be the window/join-button verdict when
    ``activity.eligible is not False``. If already gated (eligible is False),
    recover the window from signup_status == 报名进行中.

    When participation rules were never observed (list payloads without
    allowYear/allowCollege), keep eligible=None instead of treating empty
    lists as unrestricted.
    """
    if activity.eligible is False:
        window_allow = activity.signup_status == "报名进行中"
    else:
        window_allow = activity.allow_signup
    if not activity.participation_rules_known:
        return activity.model_copy(
            update={
                "eligible": None,
                "ineligible_reason": None,
                "allow_signup": bool(window_allow),
            }
        )
    eligible, reason = evaluate_eligibility(
        activity.allowed_years,
        activity.allowed_colleges,
        user_year=user_year,
        user_college=user_college,
    )
    return activity.model_copy(
        update={
            "eligible": eligible,
            "ineligible_reason": reason,
            "allow_signup": bool(window_allow) and (eligible is not False),
        }
    )


def parse_activity(
    raw: dict[str, Any],
    *,
    now: datetime | None = None,
    user_year: str | None = None,
    user_college: str | None = None,
) -> Activity:
    raw = _flatten_nested_activity_fields(raw)
    activity_id = _first(raw, ID_FIELDS)
    title = _first(raw, TITLE_FIELDS)
    if not activity_id or not title:
        raise ParseError("activity is missing id or title")
    score_items = _score_items(raw)
    credits = " / ".join(f"{item.label}:{item.value}{item.unit}" for item in score_items) or None
    content = _first(raw, CONTENT_FIELDS)
    human_status = _first(raw, STATUS_NAME_FIELDS)
    status_code_value = _first(raw, STATUS_CODE_FIELDS)
    status_code = str(status_code_value) if status_code_value is not None else None
    # statusName is the human label; known numeric codes map when the name is missing.
    if human_status is not None:
        status = str(human_status)
    elif status_code is not None and status_code.isdigit():
        status = STATUS_CODE_LABELS.get(status_code)
    else:
        status = status_code
    signup_start_time = _parse_datetime(_first(raw, SIGNUP_START_FIELDS))
    signup_end_time = _parse_datetime(_first(raw, SIGNUP_END_FIELDS))
    signup_status, window_allow = _parse_signup_state(
        raw, signup_start=signup_start_time, signup_end=signup_end_time, now=now
    )
    rules_known = participation_rules_known_in_raw(raw)
    allowed_years = _allow_name_list(raw, "allowYear", "allow_year")
    allowed_colleges = _allow_name_list(raw, "allowCollege", "allow_college")
    if rules_known:
        eligible, ineligible_reason = evaluate_eligibility(
            allowed_years,
            allowed_colleges,
            user_year=user_year,
            user_college=user_college,
        )
    else:
        eligible, ineligible_reason = None, None
    allow_signup = bool(window_allow) and (eligible is not False)
    # list/myList lack type names; detail has categoryName after flattening baseInfo.
    return Activity(
        activity_id=str(activity_id),
        title=str(title),
        activity_type=str(_first(raw, TYPE_FIELDS, "未知")),
        start_time=_parse_datetime(_first(raw, START_FIELDS)),
        end_time=_parse_datetime(_first(raw, END_FIELDS)),
        signup_start_time=signup_start_time,
        signup_end_time=signup_end_time,
        location=_first(raw, LOCATION_FIELDS),
        organizer=_first(raw, ORGANIZER_FIELDS),
        content=content,
        status=status,
        status_code=status_code,
        signup_status=signup_status,
        allow_signup=allow_signup,
        signed_in=_parse_signed_in(raw),
        credits=credits,
        score_items=score_items,
        allowed_years=allowed_years,
        allowed_colleges=allowed_colleges,
        participation_rules_known=rules_known,
        eligible=eligible,
        ineligible_reason=ineligible_reason,
        raw=raw,
    )


def parse_activity_list(
    response: dict[str, Any],
    *,
    now: datetime | None = None,
    user_year: str | None = None,
    user_college: str | None = None,
) -> list[Activity]:
    data = _data(response)
    if isinstance(data, dict):
        items = data.get("list") or data.get("items") or data.get("rows") or []
    elif isinstance(data, list):
        items = data
    else:
        raise ParseError("activity list data is invalid")
    return [
        parse_activity(item, now=now, user_year=user_year, user_college=user_college)
        for item in items
    ]


def parse_activity_detail(
    response: dict[str, Any],
    *,
    activity_id: str | None = None,
    now: datetime | None = None,
    user_year: str | None = None,
    user_college: str | None = None,
) -> Activity:
    data = _data(response)
    if not isinstance(data, dict):
        raise ParseError("activity detail data is invalid")
    payload = _flatten_nested_activity_fields(data)
    if _first(payload, ID_FIELDS) in (None, "") and activity_id not in (None, ""):
        payload["id"] = activity_id
    return parse_activity(payload, now=now, user_year=user_year, user_college=user_college)
