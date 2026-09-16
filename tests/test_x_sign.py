from __future__ import annotations

import base64
import json
import re
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from pu_mcp.x_sign import generate_x_sign

# Public PU web client protocol key (same as PU-SignUpBot); used only to decrypt in tests.
_X_SIGN_KEY = bytes([121, 121, 0, 19, 5, 49, 2, 43, 13, 17, 11, 9, 4, 29, 60, 11])

# Fixed vector: echo=abcdefghijklmnop, timestamp="1700000000", iv=bytes(range(16))
_FIXED_ECHO = "abcdefghijklmnop"
_FIXED_TIMESTAMP = "1700000000"
_FIXED_IV = bytes(range(16))
_FIXED_N = (
    "AAECAwQFBgcICQoLDA0OD++SIVfEpezO3qV8gi1lPwB7KEBuVN5USE9heEfXJIqh"
    "KJroX8EqANHV20EX1n5l5CICGh7l7lnCHNQdbpaXsT2VbG+yMcclc2Da+TtAMRP8"
)


def _decrypt_x_sign(n: str) -> tuple[bytes, dict]:
    raw = base64.b64decode(n)
    iv, ciphertext = raw[:16], raw[16:]
    decryptor = Cipher(algorithms.AES(_X_SIGN_KEY), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return iv, json.loads(plaintext.decode("utf-8"))


def test_generate_x_sign_is_deterministic_with_injected_echo_timestamp_iv():
    n = generate_x_sign(echo=_FIXED_ECHO, timestamp=_FIXED_TIMESTAMP, iv=_FIXED_IV)
    assert n == _FIXED_N


def test_generate_x_sign_roundtrip_payload_is_compact_json_with_string_timestamp():
    n = generate_x_sign(echo=_FIXED_ECHO, timestamp=_FIXED_TIMESTAMP, iv=_FIXED_IV)
    iv, payload = _decrypt_x_sign(n)
    assert iv == _FIXED_IV
    assert payload == {
        "echo": _FIXED_ECHO,
        "timestamp": _FIXED_TIMESTAMP,
        "client": "web",
    }
    assert isinstance(payload["timestamp"], str)
    raw = base64.b64decode(n)
    plaintext_len = len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    assert len(raw) == 16 + ((plaintext_len + 15) // 16) * 16


def test_generate_x_sign_without_args_uses_web_client_and_string_unix_timestamp():
    before = int(time.time())
    n = generate_x_sign()
    after = int(time.time())
    _iv, payload = _decrypt_x_sign(n)
    assert payload["client"] == "web"
    assert re.fullmatch(r"[A-Za-z0-9]{16}", payload["echo"])
    assert isinstance(payload["timestamp"], str)
    assert payload["timestamp"].isdigit()
    ts = int(payload["timestamp"])
    assert before <= ts <= after
