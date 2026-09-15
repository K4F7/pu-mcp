from __future__ import annotations

from pathlib import Path

import pytest

from pu_mcp.config import Settings, default_data_dir, default_db_path
from pu_mcp.mcp_launch import LEGACY_SESSION_FALLBACK_DIRNAME, SESSION_FALLBACK_DIRNAME


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def test_default_data_dir_uses_new_dirname(fake_home):
    path = default_data_dir()
    assert path == fake_home / SESSION_FALLBACK_DIRNAME
    assert path.is_dir()


def test_default_db_path_uses_new_when_neither_exists(fake_home):
    path = default_db_path()
    assert path == fake_home / SESSION_FALLBACK_DIRNAME / "pu.sqlite"
    assert not (fake_home / LEGACY_SESSION_FALLBACK_DIRNAME / "pu.sqlite").exists()


def test_default_db_path_migrates_legacy_sqlite(fake_home):
    legacy = fake_home / LEGACY_SESSION_FALLBACK_DIRNAME
    legacy.mkdir(parents=True)
    legacy_db = legacy / "pu.sqlite"
    legacy_db.write_bytes(b"legacy-sqlite-bytes")
    new_db = fake_home / SESSION_FALLBACK_DIRNAME / "pu.sqlite"
    assert not new_db.exists()

    path = default_db_path()
    assert path == new_db
    assert new_db.is_file()
    assert new_db.read_bytes() == b"legacy-sqlite-bytes"
    # legacy retained (copy, not move)
    assert legacy_db.is_file()


def test_default_db_path_prefers_new_over_legacy(fake_home):
    legacy = fake_home / LEGACY_SESSION_FALLBACK_DIRNAME
    legacy.mkdir(parents=True)
    (legacy / "pu.sqlite").write_bytes(b"old")
    new_dir = fake_home / SESSION_FALLBACK_DIRNAME
    new_dir.mkdir(parents=True)
    (new_dir / "pu.sqlite").write_bytes(b"new")

    path = default_db_path()
    assert path == new_dir / "pu.sqlite"
    assert path.read_bytes() == b"new"


def test_settings_db_path_uses_default_db_path(fake_home):
    settings = Settings()
    assert settings.db_path == default_db_path()
