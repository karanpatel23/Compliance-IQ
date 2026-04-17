import os
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.getenv("APP_ENCRYPTION_KEY")
    if not key:
        # Deterministic fallback for local dev only.
        key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    return Fernet(key.encode())


def encrypt_text(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
