from __future__ import annotations

import json
import os
import stat
import subprocess
import warnings
from pathlib import Path

import keyring
from pydantic import TypeAdapter

from pu_mcp.config import default_data_dir
from pu_mcp.mcp_launch import (
    LEGACY_SESSION_FALLBACK_DIRNAME,
    SESSION_FALLBACK_FILENAME,
    SESSION_FALLBACK_POSIX_MODE,
)
from pu_mcp.models import AuthSession

SERVICE_NAME = "pu-mcp"
LEGACY_SERVICE_NAME = "pu-tool"
_KEYRING_KEYS = ("token", "sid", "metadata")


def mask_secret(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return f"{value[:1]}...{value[-1:]}"
    return f"{value[:4]}...{value[-4:]}"


class SessionStore:
    def save(self, session: AuthSession) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def load(self) -> AuthSession | None:  # pragma: no cover - interface
        raise NotImplementedError

    def clear(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class FileSessionStore(SessionStore):
    def __init__(self, path: Path | None = None):
        self.path = path or default_data_dir() / SESSION_FALLBACK_FILENAME

    def _legacy_path(self) -> Path:
        return Path.home() / LEGACY_SESSION_FALLBACK_DIRNAME / SESSION_FALLBACK_FILENAME

    def save(self, session: AuthSession) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(session.model_dump_json(), encoding="utf-8")
        self._restrict_permissions()

    def load(self) -> AuthSession | None:
        if self.path.exists():
            return self._read(self.path)
        legacy = self._legacy_path()
        if not legacy.exists():
            return None
        session = self._read(legacy)
        self.save(session)
        return session

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self._legacy_path().unlink(missing_ok=True)

    def _read(self, path: Path) -> AuthSession:
        return TypeAdapter(AuthSession).validate_json(path.read_text(encoding="utf-8"))

    def _restrict_permissions(self) -> None:
        if os.name == "posix":
            self.path.chmod(SESSION_FALLBACK_POSIX_MODE)
            return
        self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
        username = os.environ.get("USERNAME")
        if not username:
            return
        account = username
        domain = os.environ.get("USERDOMAIN")
        if domain:
            account = f"{domain}\\{username}"
        subprocess.run(
            [
                "icacls",
                str(self.path),
                "/inheritance:r",
                "/grant:r",
                f"{account}:RW",
            ],
            check=False,
            capture_output=True,
            text=True,
        )


class KeyringSessionStore(SessionStore):
    def __init__(self, fallback: FileSessionStore | None = None):
        self.fallback = fallback or FileSessionStore()

    def save(self, session: AuthSession) -> None:
        try:
            keyring.set_password(SERVICE_NAME, "token", session.token)
            keyring.set_password(SERVICE_NAME, "sid", session.sid)
            metadata = session.model_copy(update={"token": "", "sid": ""}).model_dump_json()
            keyring.set_password(SERVICE_NAME, "metadata", metadata)
        except Exception:
            warnings.warn(
                "OS keyring 不可用，改用本地文件保存 session；请注意本地文件保护。"
                f" fallback={self.fallback.path}",
                RuntimeWarning,
                stacklevel=2,
            )
            self.fallback.save(session)

    def load(self) -> AuthSession | None:
        try:
            session = self._load_from_service(SERVICE_NAME)
            if session is not None:
                return session
            session = self._load_from_service(LEGACY_SERVICE_NAME)
            if session is not None:
                self.save(session)
                return session
        except Exception:
            return self.fallback.load()
        return self.fallback.load()

    def clear(self) -> None:
        for service in (SERVICE_NAME, LEGACY_SERVICE_NAME):
            for key in _KEYRING_KEYS:
                try:
                    keyring.delete_password(service, key)
                except Exception:
                    pass
        self.fallback.clear()

    def _load_from_service(self, service: str) -> AuthSession | None:
        token = keyring.get_password(service, "token")
        sid = keyring.get_password(service, "sid")
        metadata = keyring.get_password(service, "metadata")
        if not (token and sid):
            return None
        values = json.loads(metadata or "{}")
        values.update({"token": token, "sid": sid})
        return AuthSession.model_validate(values)
