from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

FixtureLoader = Callable[[str], dict]


@pytest.fixture
def fixture_json() -> FixtureLoader:
    fixture_dir = Path(__file__).parent / "fixtures"

    def load(name: str) -> dict:
        with (fixture_dir / name).open(encoding="utf-8") as fp:
            return json.load(fp)

    return load


@pytest.fixture(autouse=True)
def block_live_pu_network(monkeypatch):
    original_async = httpx.AsyncHTTPTransport.handle_async_request
    original_sync = httpx.HTTPTransport.handle_request

    async def guarded_async(self, request):
        if request.url.host == "apis.pocketuni.net":
            raise AssertionError("tests must not call the real PU API")
        return await original_async(self, request)

    def guarded_sync(self, request):
        if request.url.host == "apis.pocketuni.net":
            raise AssertionError("tests must not call the real PU API")
        return original_sync(self, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", guarded_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", guarded_sync)
