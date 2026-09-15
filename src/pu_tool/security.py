from __future__ import annotations

import json
import os
import stat
import subprocess
import warnings
from pathlib import Path

import keyring
from pydantic import TypeAdapter

from pu_tool.config import default_data_dir
from pu_tool.mcp_launch import SESSION_FALLBACK_FILENAME, SESSION_FALLBACK_POSIX_MODE
from pu_tool.models import AuthSession

SERVICE_NAME = "pu-tool"


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

    def save(self, session: AuthSession) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(session.model_dump_json(), encoding="utf-8")
        self._restrict_permissions()

    def load(self) -> AuthSession | None:
        if not self.path.exists():
            return None
        return TypeAdapter(AuthSession).validate_json(self.path.read_text(encoding="utf-8"))

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

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
            token = keyring.get_password(SERVICE_NAME, "token")
            sid = keyring.get_password(SERVICE_NAME, "sid")
            metadata = keyring.get_password(SERVICE_NAME, "metadata")
            if token and sid:
                values = json.loads(metadata or "{}")
                values.update({"token": token, "sid": sid})
                return AuthSession.model_validate(values)
        except Exception:
            return self.fallback.load()
        return self.fallback.load()

    def clear(self) -> None:
        for key in ("token", "sid", "metadata"):
            try:
                keyring.delete_password(SERVICE_NAME, key)
            except Exception:
                pass
        self.fallback.clear()
