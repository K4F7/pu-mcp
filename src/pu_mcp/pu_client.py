from __future__ import annotations

import asyncio
import base64
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from pu_mcp.errors import AuthError, BusinessError, NetworkError, RateLimitError, RiskControlError
from pu_mcp.models import AuthSession

RISK_WORDS = ("验证码", "captcha", "风控", "风险", "异常登录", "设备")
SID_XOR_KEY = "sid"


def decode_school_sid(encoded_sid: str) -> str:
    value = encoded_sid.strip()
    parsed = urlparse(value)
    queries = [parsed.query]
    if parsed.fragment:
        fragment_query = urlparse(parsed.fragment).query
        if not fragment_query and "?" in parsed.fragment:
            fragment_query = parsed.fragment.split("?", 1)[1]
        queries.append(fragment_query)
    for query in queries:
        sid_values = parse_qs(query).get("sid")
        if sid_values:
            value = sid_values[0]
            break

    decoded = base64.b64decode(value).decode("utf-8")
    chars = [
        chr(ord(char) ^ ord(SID_XOR_KEY[index % len(SID_XOR_KEY)]))
        for index, char in enumerate(decoded)
    ]
    return "".join(chars)


class PuClient:
    def __init__(
        self,
        base_url: str,
        session: AuthSession | None = None,
        timeout_seconds: float = 10,
        min_interval_seconds: float = 2,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = min_interval_seconds
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_seconds)
        self._last_request = 0.0
        self._request_lock = asyncio.Lock()

    async def __aenter__(self) -> PuClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait_for = self.min_interval_seconds - elapsed
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        self._last_request = time.monotonic()

    def _headers(self, authenticated: bool) -> dict[str, str]:
        if not authenticated:
            return {}
        if not self.session:
            raise AuthError("not authenticated")
        return {"Authorization": f"Bearer {self.session.token}:{self.session.sid}"}

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with self._request_lock:
                    await self._throttle()
                    kwargs: dict[str, Any] = {"headers": self._headers(authenticated)}
                    if method.upper() != "GET":
                        kwargs["json"] = payload or {}
                    response = await self._client.request(method, path, **kwargs)
                if response.status_code >= 500:
                    if attempt < attempts - 1:
                        await asyncio.sleep(0.05 * (2**attempt))
                        continue
                    raise NetworkError(f"server error: {response.status_code}")
                if response.status_code == 401:
                    raise AuthError("authentication failed")
                if response.status_code == 429:
                    raise RateLimitError("rate limited")
                data = response.json()
                self._raise_for_payload(data)
                return data
            except (BusinessError, RiskControlError, AuthError, RateLimitError):
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(0.05 * (2**attempt))
                    continue
                raise NetworkError(str(exc)) from exc
        raise NetworkError(str(last_error or "network error"))

    async def _post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        return await self._request("POST", path, payload, authenticated=authenticated)

    async def _get(
        self,
        path: str,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        return await self._request("GET", path, authenticated=authenticated)

    def _raise_for_payload(self, data: dict[str, Any]) -> None:
        code = data.get("code", 0)
        message = str(data.get("msg") or data.get("message") or "")
        lowered = message.lower()
        if code in (0, "0", 200, "200"):
            return
        if any(word.lower() in lowered for word in RISK_WORDS):
            raise RiskControlError(message)
        if code in (401, "401"):
            raise AuthError(message or "authentication failed")
        if code in (429, "429"):
            raise RateLimitError(message or "rate limited")
        raise BusinessError(message or f"business error: {code}")

    async def login(self, username: str, password: str, school_sid: str) -> AuthSession:
        data = await self._post(
            "/uc/user/login",
            {
                "userName": username,
                "password": password,
                "sid": int(school_sid),
                "device": "pc",
            },
            authenticated=False,
        )
        payload = data.get("data") or {}
        token = payload.get("token")
        sid = payload.get("sid")
        if not token or not sid:
            raise AuthError("login response missing token or sid")
        user = payload.get("baseUserInfo") or payload.get("user") or {}
        session = AuthSession(
            token=str(token), sid=str(sid), masked_user=str(user.get("account") or username)
        )
        self.session = session
        return session

    async def school_list(self) -> list[dict[str, Any]]:
        data = await self._get("/uc/school/list", authenticated=False)
        payload = data.get("data") or {}
        return list(payload.get("list") or [])

    async def activity_list(self, **filters: Any) -> dict[str, Any]:
        payload = {"page": 1, "limit": 20, **filters}
        return await self._post("/apis/activity/list", payload)

    async def activity_info(self, activity_id: str) -> dict[str, Any]:
        return await self._post("/apis/activity/info", {"id": activity_id})

    async def join_activity(self, activity_id: str) -> dict[str, Any]:
        return await self._post("/apis/activity/join", {"id": activity_id})

    async def my_list(self, **filters: Any) -> dict[str, Any]:
        payload = {"type": 1, "page": 1, "limit": 20, **filters}
        return await self._post("/apis/activity/myList", payload)
