from __future__ import annotations

import os
import stat

import pytest

from pu_tool.models import AuthSession
from pu_tool.security import FileSessionStore, KeyringSessionStore, mask_secret


def test_mask_secret_never_returns_full_value():
    assert mask_secret("test-token-abcdef123456") != "test-token-abcdef123456"
    assert "abcdef123456" not in mask_secret("test-token-abcdef123456")
    assert mask_secret(None) == "<empty>"


def test_file_session_store_round_trips_without_password(tmp_path):
    store = FileSessionStore(tmp_path / "session.json")
    session = AuthSession(
        token="test-token-abcdef123456", sid="test-sid-654321", masked_user="demo"
    )
    store.save(session)
    raw = (tmp_path / "session.json").read_text(encoding="utf-8")
    assert "password" not in raw.lower()
    assert store.load() == session


def test_file_session_store_restricts_file_permissions(tmp_path):
    path = tmp_path / "session.json"
    store = FileSessionStore(path)
    store.save(AuthSession(token="token", sid="sid", masked_user="demo"))

    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        assert not (path.stat().st_file_attributes & getattr(stat, "FILE_ATTRIBUTE_READONLY", 0))


def test_keyring_unavailable_warns_with_concrete_fallback_path(monkeypatch, tmp_path):
    fallback_path = tmp_path / "session.json"
    store = KeyringSessionStore(fallback=FileSessionStore(fallback_path))

    def boom(*_args, **_kwargs):
        raise OSError("keyring backend unavailable")

    monkeypatch.setattr("pu_tool.security.keyring.set_password", boom)

    session = AuthSession(token="token", sid="sid", masked_user="demo")
    with pytest.warns(RuntimeWarning) as caught:
        store.save(session)

    messages = " ".join(str(item.message) for item in caught)
    fallback = store.fallback.path
    assert str(fallback) in messages or fallback.as_posix() in messages
    assert fallback == fallback_path
    assert fallback_path.is_file()
    assert fallback_path.is_relative_to(tmp_path)
    raw = fallback_path.read_text(encoding="utf-8")
    assert "password" not in raw.lower()
