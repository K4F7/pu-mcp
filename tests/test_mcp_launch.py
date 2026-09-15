from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GROK_CONFIG = REPO_ROOT / ".grok" / "config.toml"
GROK_BOT_DOC = REPO_ROOT / "docs" / "agents" / "grok-bot-linux-mcp.md"
README = REPO_ROOT / "README.md"
_FENCE_BLOCK = re.compile(r"^```([^\n]*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
_SHELL_FENCE_LANGS = {"", "bash", "sh", "shell", "zsh", "console", "powershell", "pwsh", "cmd"}


def _mcp_launch():
    from pu_mcp.mcp_launch import (
        MCP_COMMAND,
        MCP_DIRECTORY_FLAG,
        MCP_DIRECTORY_PLACEHOLDER,
        MCP_STARTUP_TIMEOUT_SEC,
        MCP_STDIO_ARGS,
        SESSION_FALLBACK_DIRNAME,
        SESSION_FALLBACK_FILENAME,
        SESSION_FALLBACK_POSIX_MODE,
    )

    return {
        "command": MCP_COMMAND,
        "directory_flag": MCP_DIRECTORY_FLAG,
        "directory_placeholder": MCP_DIRECTORY_PLACEHOLDER,
        "startup_timeout_sec": MCP_STARTUP_TIMEOUT_SEC,
        "stdio_args": MCP_STDIO_ARGS,
        "fallback_dirname": SESSION_FALLBACK_DIRNAME,
        "fallback_filename": SESSION_FALLBACK_FILENAME,
        "fallback_posix_mode": SESSION_FALLBACK_POSIX_MODE,
    }


def _pu_mcp_config() -> dict:
    parsed = tomllib.loads(GROK_CONFIG.read_text(encoding="utf-8"))
    return parsed["mcp_servers"]["pu"]


def _json_lists(text: str) -> list[list[object]]:
    found: list[list[object]] = []
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        start = text.find("[", idx)
        if start < 0:
            return found
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(value, list):
            found.append(value)
        idx = end


def _directory_launch_args(text: str) -> list[object]:
    for item in _json_lists(text):
        if item and item[0] == "--directory":
            return item
    raise AssertionError("no JSON args array starting with --directory")


def _grok_bot_doc() -> str:
    assert GROK_BOT_DOC.is_file(), f"missing {GROK_BOT_DOC.as_posix()}"
    return GROK_BOT_DOC.read_text(encoding="utf-8")


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _shell_fence_languages(text: str) -> list[str]:
    langs: list[str] = []
    for match in _FENCE_BLOCK.finditer(text):
        raw = match.group(1).strip()
        lang = raw.split()[0].lower() if raw else ""
        if lang in _SHELL_FENCE_LANGS:
            langs.append(lang)
    return langs


def test_launch_constants_use_renamed_package_paths():
    launch = _mcp_launch()
    assert launch["directory_placeholder"] == "/path/to/pu-mcp"
    assert launch["fallback_dirname"] == ".pu_mcp"
    assert launch["fallback_filename"] == "session.json"
    assert launch["fallback_posix_mode"] == 0o600
    assert launch["stdio_args"][-2:] == ["pu", "mcp"]


def test_pyproject_package_name_is_pu_mcp():
    parsed = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert parsed["project"]["name"] == "pu-mcp"
    assert parsed["project"]["scripts"]["pu"] == "pu_mcp.cli:app"
    assert parsed["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/pu_mcp"]


def test_grok_config_toml_independent_repo_root_shape():
    config = _pu_mcp_config()
    args = config["args"]
    assert config["command"] == "uv"
    assert config["command"] != "pu"
    assert config["startup_timeout_sec"] == 60
    assert "--directory" not in args
    assert args[-2:] == ["pu", "mcp"]
    assert "--no-sync" in args
    assert "3.12" in args
    assert args == ["run", "--python", "3.12", "--no-sync", "pu", "mcp"]


def test_grok_config_toml_matches_launch_constants():
    launch = _mcp_launch()
    config = _pu_mcp_config()
    assert config["command"] == launch["command"]
    assert config["args"] == launch["stdio_args"]
    assert config["startup_timeout_sec"] == launch["startup_timeout_sec"]


def test_grok_bot_linux_mcp_doc_exists():
    assert GROK_BOT_DOC.is_file()


def test_grok_bot_linux_mcp_doc_directory_launch_independent_shape():
    source = _grok_bot_doc()
    extracted = _directory_launch_args(source)
    assert "--directory" in source
    assert extracted[0] == "--directory"
    assert extracted[1] == "/path/to/pu-mcp"
    config_args = _pu_mcp_config()["args"]
    assert extracted[2:] == config_args


def test_grok_bot_linux_mcp_doc_args_match_launch_constants():
    launch = _mcp_launch()
    extracted = _directory_launch_args(_grok_bot_doc())
    expected = [
        launch["directory_flag"],
        launch["directory_placeholder"],
        *launch["stdio_args"],
    ]
    assert extracted == expected
    assert extracted[2:] == launch["stdio_args"]


def test_grok_bot_linux_mcp_doc_command_is_uv_not_pu():
    source = _grok_bot_doc()
    command_uv = bool(
        re.search(r'command\s*=\s*"uv"', source)
        or re.search(r'"command"\s*:\s*"uv"', source)
        or re.search(r"command\s*[:=]\s*`uv`", source)
    )
    command_pu = bool(
        re.search(r'command\s*=\s*"pu"', source) or re.search(r'"command"\s*:\s*"pu"', source)
    )
    assert command_uv
    assert not command_pu


def test_grok_bot_linux_mcp_doc_addmcp_has_no_cwd():
    source = _grok_bot_doc()
    assert "AddMcpServer" in source
    assert re.search(
        r"(no cwd|without cwd|NO cwd|没有\s*cwd|不含\s*cwd|无\s*cwd|不支持\s*cwd|不提供\s*cwd)",
        source,
        re.I,
    )


def test_grok_bot_linux_mcp_doc_onboarding_and_keyring_fallback():
    source = _grok_bot_doc()
    assert "clone" in source.lower() or "克隆" in source
    assert "uv sync --python 3.12 --extra dev" in source
    assert "/path/to/pu-mcp" in source
    assert "pu login --sid" in source
    assert "AddMcpServer" in source
    assert "~/.pu_mcp/session.json" in source or (
        ".pu_mcp" in source and "session.json" in source
    )
    assert "0600" in source or "0o600" in source
    assert re.search(r"(less secure|更不安全|安全性低于|不如)", source, re.I)
    assert re.search(r"(never commit|不要提交|不可提交|绝不提交|禁止提交|勿提交)", source, re.I)
    assert re.search(r"(明文密码|不保存密码|不存储密码|passwords never|never stored)", source, re.I)


def test_readme_documents_required_launch_commands():
    source = _readme()
    assert "uv sync --python 3.12 --extra dev" in source
    assert "pu login --sid" in source
    assert "uv run --python 3.12 --no-sync pu mcp" in source


def test_readme_explains_uv_on_path_and_no_global_pu():
    source = _readme()
    assert re.search(r"(install uv|安装\s*`?uv`?)", source, re.I)
    assert "PATH" in source
    assert "--python 3.12" in source
    assert "uv run" in source
    assert re.search(
        r"(need not|does not need|不必|无需|不用全局|不必全局|无需全局|不必把 pu|无需把 pu)",
        source,
        re.I,
    )


def test_readme_not_windows_only_shell_examples():
    shell_langs = _shell_fence_languages(_readme())
    has_non_powershell = any(lang not in {"powershell", "pwsh", "cmd"} for lang in shell_langs)
    has_powershell = any(lang in {"powershell", "pwsh"} for lang in shell_langs)
    has_unix = any(lang in {"bash", "sh", "shell", "zsh"} for lang in shell_langs)
    assert has_non_powershell or (has_powershell and has_unix)


def test_readme_links_grok_bot_linux_mcp_doc():
    source = _readme()
    assert "docs/agents/grok-bot-linux-mcp.md" in source


def test_readme_documents_keyring_fallback_risk():
    source = _readme()
    assert "~/.pu_mcp/session.json" in source or (
        ".pu_mcp" in source and "session.json" in source
    )
    assert "0600" in source or "0o600" in source
    assert re.search(r"(less secure|更不安全|安全性低于|不如)", source, re.I)
    assert re.search(r"(protect|保护)", source, re.I)
    assert re.search(r"(never commit|不要提交|不可提交|绝不提交|禁止提交|勿提交)", source, re.I)
    assert re.search(r"(明文密码|不保存密码|不存储密码|passwords never|never stored)", source, re.I)


def test_readme_distinguishes_cwd_config_from_directory_form():
    source = _readme()
    assert ".grok/config.toml" in source
    assert "--directory" in source
    assert re.search(r"(cwd|仓库根|repo root)", source, re.I)
    assert re.search(r"Grok Bot", source, re.I)


def test_readme_keyring_fallback_matches_launch_constants():
    launch = _mcp_launch()
    source = _readme()
    assert launch["fallback_dirname"] in source
    assert launch["fallback_filename"] in source
    mode = format(launch["fallback_posix_mode"], "o")
    assert mode in source or f"0o{mode}" in source or f"0{mode}" in source


@pytest.mark.asyncio
async def test_mcp_tools_unchanged_and_still_no_login():
    from pu_mcp.mcp_server import mcp
    from test_mcp import EXPECTED_MCP_TOOLS, FORBIDDEN_MCP_TOOLS

    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert names == EXPECTED_MCP_TOOLS
    assert names.isdisjoint(FORBIDDEN_MCP_TOOLS)
    assert "login" not in names
