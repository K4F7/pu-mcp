from __future__ import annotations

import base64
import json
import secrets
import string
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

# Public PU web client / PU-SignUpBot protocol key (AES-128).
_X_SIGN_KEY = bytes([121, 121, 0, 19, 5, 49, 2, 43, 13, 17, 11, 9, 4, 29, 60, 11])
_ECHO_ALPHABET = string.ascii_letters + string.digits


def generate_random_echo(length: int = 16) -> str:
    return "".join(secrets.choice(_ECHO_ALPHABET) for _ in range(length))


def current_timestamp_str() -> str:
    return str(int(time.time()))


def _aes_cbc_encrypt_pkcs7(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def encrypt_payload_to_n(payload: dict[str, str], iv: bytes | None = None) -> str:
    if iv is None:
        iv = secrets.token_bytes(16)
    if len(iv) != 16:
        raise ValueError("IV must be 16 bytes")
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = _aes_cbc_encrypt_pkcs7(plaintext, _X_SIGN_KEY, iv)
    return base64.b64encode(iv + ciphertext).decode("ascii")


def generate_x_sign(
    echo: str | None = None,
    timestamp: str | None = None,
    client: str = "web",
    iv: bytes | None = None,
) -> str:
    if echo is None:
        echo = generate_random_echo()
    if timestamp is None:
        timestamp = current_timestamp_str()
    payload = {"echo": echo, "timestamp": timestamp, "client": client}
    return encrypt_payload_to_n(payload, iv=iv)
