from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from pu_mcp.models import AuthSession
from pu_mcp.security import SERVICE_NAME, FileSessionStore, KeyringSessionStore, mask_secret

NEW_SERVICE_NAME = "pu-mcp"
LEGACY_SERVICE_NAME = "pu-tool"
NEW_DIRNAME = ".pu_mcp"
LEGACY_DIRNAME = ".pu_tool"
SESSION_FILENAME = "session.json"


class MemoryKeyring:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._data[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._data.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self._data[(service, username)]
        except KeyError as exc:
            raise RuntimeError("password not found") from exc


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda *args, **kwargs: home)
    return home


@pytest.fixture
def memory_keyring(monkeypatch) -> MemoryKeyring:
    backend = MemoryKeyring()
    monkeypatch.setattr("pu_mcp.security.keyring.set_password", backend.set_password)
    monkeypatch.setattr("pu_mcp.security.keyring.get_password", backend.get_password)
    monkeypatch.setattr("pu_mcp.security.keyring.delete_password", backend.delete_password)
    return backend


def _session(**overrides) -> AuthSession:
    values = {
        "token": "test-token-abcdef123456",
        "sid": "test-sid-654321",
        "masked_user": "demo",
    }
    values.update(overrides)
    return AuthSession(**values)


def _write_session_file(path: Path, session: AuthSession) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(), encoding="utf-8")


def _put_keyring_session(backend: MemoryKeyring, service: str, session: AuthSession) -> None:
    backend.set_password(service, "token", session.token)
    backend.set_password(service, "sid", session.sid)
    metadata = session.model_copy(update={"token": "", "sid": ""}).model_dump_json()
    backend.set_password(service, "metadata", metadata)


def _posix_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


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

    monkeypatch.setattr("pu_mcp.security.keyring.set_password", boom)

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


def test_keyring_service_name_is_pu_mcp():
    assert SERVICE_NAME == NEW_SERVICE_NAME
    assert SERVICE_NAME != LEGACY_SERVICE_NAME


def test_file_session_store_default_path_uses_new_home_dir(fake_home):
    store = FileSessionStore()
    assert store.path == fake_home / NEW_DIRNAME / SESSION_FILENAME
    assert store.path != fake_home / LEGACY_DIRNAME / SESSION_FILENAME


def test_file_session_store_loads_legacy_home_session(fake_home):
    session = _session(token="legacy-token", sid="legacy-sid", masked_user="legacy")
    legacy_path = fake_home / LEGACY_DIRNAME / SESSION_FILENAME
    new_path = fake_home / NEW_DIRNAME / SESSION_FILENAME
    _write_session_file(legacy_path, session)
    assert not new_path.exists()

    store = FileSessionStore()
    assert store.path == new_path
    assert store.load() == session


def test_file_session_store_migrates_legacy_on_read(fake_home):
    session = _session(token="legacy-token", sid="legacy-sid", masked_user="legacy")
    legacy_path = fake_home / LEGACY_DIRNAME / SESSION_FILENAME
    new_path = fake_home / NEW_DIRNAME / SESSION_FILENAME
    _write_session_file(legacy_path, session)

    store = FileSessionStore()
    loaded = store.load()
    assert loaded == session
    assert new_path.is_file()
    assert "password" not in new_path.read_text(encoding="utf-8").lower()
    if os.name == "posix":
        assert _posix_mode(new_path) == 0o600
    assert store.load() == session


def test_file_session_store_save_writes_new_home_dir_only(fake_home):
    session = _session()
    store = FileSessionStore()
    store.save(session)

    new_path = fake_home / NEW_DIRNAME / SESSION_FILENAME
    legacy_path = fake_home / LEGACY_DIRNAME / SESSION_FILENAME
    assert new_path.is_file()
    assert not legacy_path.exists()
    assert store.load() == session
    assert "password" not in new_path.read_text(encoding="utf-8").lower()
    if os.name == "posix":
        assert _posix_mode(new_path) == 0o600


def test_file_session_store_prefers_new_over_legacy_when_both_present(fake_home):
    new_session = _session(token="new-token", sid="new-sid", masked_user="new")
    old_session = _session(token="old-token", sid="old-sid", masked_user="old")
    _write_session_file(fake_home / NEW_DIRNAME / SESSION_FILENAME, new_session)
    _write_session_file(fake_home / LEGACY_DIRNAME / SESSION_FILENAME, old_session)

    assert FileSessionStore().load() == new_session


def test_file_session_store_clear_removes_new_and_legacy_files(fake_home):
    session = _session()
    new_path = fake_home / NEW_DIRNAME / SESSION_FILENAME
    legacy_path = fake_home / LEGACY_DIRNAME / SESSION_FILENAME
    _write_session_file(new_path, session)
    _write_session_file(legacy_path, session)

    FileSessionStore().clear()
    assert not new_path.exists()
    assert not legacy_path.exists()


def test_keyring_session_store_loads_legacy_service(fake_home, memory_keyring):
    session = _session(token="legacy-kr-token", sid="legacy-kr-sid", masked_user="legacy-kr")
    _put_keyring_session(memory_keyring, LEGACY_SERVICE_NAME, session)
    assert memory_keyring.get_password(NEW_SERVICE_NAME, "token") is None

    store = KeyringSessionStore()
    assert store.load() == session


def test_keyring_session_store_migrates_legacy_on_read(fake_home, memory_keyring):
    session = _session(token="legacy-kr-token", sid="legacy-kr-sid", masked_user="legacy-kr")
    _put_keyring_session(memory_keyring, LEGACY_SERVICE_NAME, session)

    store = KeyringSessionStore()
    assert store.load() == session
    assert memory_keyring.get_password(NEW_SERVICE_NAME, "token") == session.token
    assert memory_keyring.get_password(NEW_SERVICE_NAME, "sid") == session.sid
    metadata = json.loads(memory_keyring.get_password(NEW_SERVICE_NAME, "metadata") or "{}")
    assert metadata.get("masked_user") == session.masked_user
    memory_keyring.delete_password(LEGACY_SERVICE_NAME, "token")
    memory_keyring.delete_password(LEGACY_SERVICE_NAME, "sid")
    memory_keyring.delete_password(LEGACY_SERVICE_NAME, "metadata")
    assert store.load() == session


def test_keyring_session_store_save_writes_new_service_not_legacy(fake_home, memory_keyring):
    session = _session()
    store = KeyringSessionStore()
    store.save(session)

    assert memory_keyring.get_password(NEW_SERVICE_NAME, "token") == session.token
    assert memory_keyring.get_password(NEW_SERVICE_NAME, "sid") == session.sid
    metadata = json.loads(memory_keyring.get_password(NEW_SERVICE_NAME, "metadata") or "{}")
    assert metadata.get("masked_user") == session.masked_user
    assert metadata.get("token") == ""
    assert metadata.get("sid") == ""
    assert memory_keyring.get_password(LEGACY_SERVICE_NAME, "token") is None
    assert memory_keyring.get_password(LEGACY_SERVICE_NAME, "sid") is None
    assert memory_keyring.get_password(LEGACY_SERVICE_NAME, "metadata") is None


def test_keyring_session_store_clear_removes_new_and_legacy_stores(fake_home, memory_keyring):
    session = _session()
    new_path = fake_home / NEW_DIRNAME / SESSION_FILENAME
    legacy_path = fake_home / LEGACY_DIRNAME / SESSION_FILENAME
    _put_keyring_session(memory_keyring, NEW_SERVICE_NAME, session)
    _put_keyring_session(memory_keyring, LEGACY_SERVICE_NAME, session)
    _write_session_file(new_path, session)
    _write_session_file(legacy_path, session)

    KeyringSessionStore().clear()

    assert memory_keyring.get_password(NEW_SERVICE_NAME, "token") is None
    assert memory_keyring.get_password(NEW_SERVICE_NAME, "sid") is None
    assert memory_keyring.get_password(NEW_SERVICE_NAME, "metadata") is None
    assert memory_keyring.get_password(LEGACY_SERVICE_NAME, "token") is None
    assert memory_keyring.get_password(LEGACY_SERVICE_NAME, "sid") is None
    assert memory_keyring.get_password(LEGACY_SERVICE_NAME, "metadata") is None
    assert not new_path.exists()
    assert not legacy_path.exists()


def test_file_session_store_loads_legacy_session_without_year_college(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(
        '{"token":"legacy-token","sid":"legacy-sid","masked_user":"demo"}',
        encoding="utf-8",
    )
    store = FileSessionStore(path)
    session = store.load()
    assert session is not None
    assert session.token == "legacy-token"
    assert session.year is None
    assert session.college is None
