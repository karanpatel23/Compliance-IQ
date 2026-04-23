import base64
import hashlib
import hmac
import os
import secrets


def _get_key() -> bytes:
    key = os.getenv("APP_ENCRYPTION_KEY", "dev-only-change-me")
    return hashlib.sha256(key.encode()).digest()


def _keystream(length: int, nonce: bytes, key: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_text(value: str) -> str:
    key = _get_key()
    nonce = secrets.token_bytes(16)
    payload = value.encode()
    stream = _keystream(len(payload), nonce, key)
    cipher = bytes(a ^ b for a, b in zip(payload, stream))
    sig = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + cipher + sig).decode()


def decrypt_text(value: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode())
    nonce = raw[:16]
    sig = raw[-32:]
    cipher = raw[16:-32]
    key = _get_key()
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid encrypted payload signature")
    stream = _keystream(len(cipher), nonce, key)
    payload = bytes(a ^ b for a, b in zip(cipher, stream))
    return payload.decode()
