from __future__ import annotations

from datetime import datetime
from typing import Any

from pu_mcp.errors import ParseError
from pu_mcp.models import Activity, ScoreItem

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
SIGNUP_START_FIELDS = ("applyStartTime", "signup_start", "signupStartTime")
SIGNUP_END_FIELDS = ("applyEndTime", "signup_end", "signupEndTime")
LOCATION_FIELDS = ("address", "location", "place")
ORGANIZER_FIELDS = ("organizer", "host", "clubName")
STATUS_FIELDS = ("status", "state")
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


def parse_activity(raw: dict[str, Any]) -> Activity:
    raw = _flatten_nested_activity_fields(raw)
    activity_id = _first(raw, ID_FIELDS)
    title = _first(raw, TITLE_FIELDS)
    if not activity_id or not title:
        raise ParseError("activity is missing id or title")
    score_items = _score_items(raw)
    credits = " / ".join(f"{item.label}:{item.value}{item.unit}" for item in score_items) or None
    # list/myList lack type names; detail has categoryName after flattening baseInfo.
    return Activity(
        activity_id=str(activity_id),
        title=str(title),
        activity_type=str(_first(raw, TYPE_FIELDS, "未知")),
        start_time=_parse_datetime(_first(raw, START_FIELDS)),
        end_time=_parse_datetime(_first(raw, END_FIELDS)),
        signup_start_time=_parse_datetime(_first(raw, SIGNUP_START_FIELDS)),
        signup_end_time=_parse_datetime(_first(raw, SIGNUP_END_FIELDS)),
        location=_first(raw, LOCATION_FIELDS),
        organizer=_first(raw, ORGANIZER_FIELDS),
        status=_first(raw, STATUS_FIELDS),
        signed_in=_parse_signed_in(raw),
        credits=credits,
        score_items=score_items,
        raw=raw,
    )


def parse_activity_list(response: dict[str, Any]) -> list[Activity]:
    data = _data(response)
    if isinstance(data, dict):
        items = data.get("list") or data.get("items") or data.get("rows") or []
    elif isinstance(data, list):
        items = data
    else:
        raise ParseError("activity list data is invalid")
    return [parse_activity(item) for item in items]


def parse_activity_detail(
    response: dict[str, Any], *, activity_id: str | None = None
) -> Activity:
    data = _data(response)
    if not isinstance(data, dict):
        raise ParseError("activity detail data is invalid")
    payload = _flatten_nested_activity_fields(data)
    if _first(payload, ID_FIELDS) in (None, "") and activity_id not in (None, ""):
        payload["id"] = activity_id
    return parse_activity(payload)
