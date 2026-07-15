from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from pu_tool.errors import BusinessError, NetworkError, RiskControlError
from pu_tool.models import AuthSession
from pu_tool.pu_client import PuClient, decode_school_sid


def test_decode_school_sid_from_class_url_hash():
    assert decode_school_sid("QVpTRFBVS19QS1hRRVhS") == "237791864815616"


def test_decode_school_sid_from_class_login_url():
    assert (
        decode_school_sid("https://class.pocketuni.net/#/login?sid=QVpTRFBVS19QS1hRRVhS")
        == "237791864815616"
    )


@pytest.mark.asyncio
@respx.mock
async def test_login_success_extracts_session(fixture_json):
    route = respx.post("https://mock.local/uc/user/login").mock(
        return_value=httpx.Response(200, json=fixture_json("login_success.json"))
    )
    async with PuClient(base_url="https://mock.local", min_interval_seconds=0) as client:
        session = await client.login("demo", "secret", school_sid="237791864815616")
    assert session.token == fixture_json("login_success.json")["data"]["token"]
    assert session.sid == "test-sid-654321"
    assert session.masked_user == "demo_account"
    assert route.calls[0].request.headers["content-type"].startswith("application/json")
    assert route.calls[0].request.content == (
        b'{"userName":"demo","password":"secret","sid":237791864815616,"device":"pc"}'
    )
    assert "Authorization" not in route.calls[0].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_login_risk_control_raises(fixture_json):
    respx.post("https://mock.local/uc/user/login").mock(
        return_value=httpx.Response(200, json=fixture_json("login_risk_control.json"))
    )
    async with PuClient(base_url="https://mock.local", min_interval_seconds=0) as client:
        with pytest.raises(RiskControlError):
            await client.login("demo", "secret", school_sid="237791864815616")


@pytest.mark.asyncio
@respx.mock
async def test_class_login_uses_base_user_info_when_user_account_missing():
    respx.post("https://mock.local/uc/user/login").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "ok",
                "data": {
                    "token": "class-token",
                    "sid": "auth-sid-from-login-response",
                    "baseUserInfo": {"account": "base_account"},
                },
            },
        )
    )
    async with PuClient(base_url="https://mock.local", min_interval_seconds=0) as client:
        session = await client.login("demo", "secret", school_sid="237791864815616")
    assert session.token == "class-token"
    assert session.sid == "auth-sid-from-login-response"
    assert session.masked_user == "base_account"


@pytest.mark.asyncio
@respx.mock
async def test_authenticated_activity_calls_send_authorization(fixture_json):
    route = respx.post("https://mock.local/apis/activity/list").mock(
        return_value=httpx.Response(200, json=fixture_json("activity_list.json"))
    )
    session = AuthSession(token="TEST_TOKEN", sid="TEST_SID")
    async with PuClient(
        base_url="https://mock.local", session=session, min_interval_seconds=0
    ) as client:
        payload = await client.activity_list()
    assert payload["code"] == 0
    assert (
        route.calls[0].request.headers["Authorization"]
        == "Bearer TEST_TOKEN:TEST_SID"
    )


@pytest.mark.asyncio
@respx.mock
async def test_activity_list_sends_default_page_and_limit(fixture_json):
    route = respx.post("https://mock.local/apis/activity/list").mock(
        return_value=httpx.Response(200, json=fixture_json("activity_list.json"))
    )
    session = AuthSession(token="TEST_TOKEN", sid="TEST_SID")
    async with PuClient(
        base_url="https://mock.local", session=session, min_interval_seconds=0
    ) as client:
        await client.activity_list()

    assert route.calls[0].request.content == b'{"page":1,"limit":20}'


@pytest.mark.asyncio
@respx.mock
async def test_activity_list_accepts_explicit_limit(fixture_json):
    route = respx.post("https://mock.local/apis/activity/list").mock(
        return_value=httpx.Response(200, json=fixture_json("activity_list.json"))
    )
    session = AuthSession(token="TEST_TOKEN", sid="TEST_SID")
    async with PuClient(
        base_url="https://mock.local", session=session, min_interval_seconds=0
    ) as client:
        await client.activity_list(limit=5)

    assert route.calls[0].request.content == b'{"page":1,"limit":5}'


@pytest.mark.asyncio
@respx.mock
async def test_business_failed_join_is_not_retried(fixture_json):
    route = respx.post("https://mock.local/apis/activity/join").mock(
        return_value=httpx.Response(200, json=fixture_json("activity_join_business_fail.json"))
    )
    session = AuthSession(token="TEST_TOKEN", sid="TEST_SID")
    async with PuClient(
        base_url="https://mock.local", session=session, min_interval_seconds=0
    ) as client:
        with pytest.raises(BusinessError):
            await client.join_activity("ACT-1001")
    assert len(route.calls) == 1


@pytest.mark.asyncio
@respx.mock
async def test_transient_network_errors_are_bounded():
    route = respx.post("https://mock.local/apis/activity/info").mock(
        side_effect=httpx.ConnectError("temporary")
    )
    session = AuthSession(token="TEST_TOKEN", sid="TEST_SID")
    async with PuClient(
        base_url="https://mock.local",
        session=session,
        min_interval_seconds=0,
        max_retries=2,
    ) as client:
        with pytest.raises(NetworkError):
            await client.activity_info("ACT-1001")
    assert len(route.calls) == 3


@pytest.mark.asyncio
async def test_concurrent_requests_share_serial_throttle_window():
    sent_at: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent_at.append(time.monotonic())
        return httpx.Response(200, json={"code": 0, "data": {}})

    transport = httpx.MockTransport(handler)
    session = AuthSession(token="TEST_TOKEN", sid="TEST_SID")
    async with PuClient(
        base_url="https://mock.local",
        session=session,
        min_interval_seconds=0.03,
        max_retries=0,
    ) as client:
        await client._client.aclose()
        client._client = httpx.AsyncClient(
            base_url="https://mock.local", transport=transport, timeout=1
        )

        await asyncio.gather(
            client.activity_info("ACT-1001"),
            client.activity_info("ACT-1002"),
            client.activity_info("ACT-1003"),
        )

    assert len(sent_at) == 3
    intervals = [second - first for first, second in zip(sent_at, sent_at[1:], strict=False)]
    assert all(interval >= 0.025 for interval in intervals)
