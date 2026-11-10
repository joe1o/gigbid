"""
security.py - passwords, login sessions and token encryption.

    Passwords   : never stored as typed. We store a salted PBKDF2 hash (200k rounds), so a
                  leaked database does not reveal anyone's password.
    Sessions    : after login the browser gets a cookie "user_id|expiry|signature". The
                  signature (HMAC with APP_SECRET_KEY) means nobody can forge or edit it.
    Encryption  : marketplace/OAuth tokens are encrypted with Fernet (AES) using
                  TOKEN_ENCRYPTION_KEY before they are stored, and are never logged.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time

from cryptography.fernet import Fernet

SESSION_COOKIE = "gigbid_session"


def _secret() -> bytes:
    return (os.getenv("APP_SECRET_KEY") or "dev-only-secret-change-me").encode()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


def make_session(user_id: str, days: int = 7) -> str:
    payload = f"{user_id}|{int(time.time()) + days * 86400}"
    sig = hmac.new(_secret(), payload.encode(), "sha256").hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def read_session(token: str | None) -> str | None:
    """Return the user id if the session token is genuine and not expired."""
    if not token:
        return None
    try:
        user_id, expiry, sig = base64.urlsafe_b64decode(token.encode()).decode().split("|")
    except (ValueError, UnicodeDecodeError):
        return None
    good = hmac.new(_secret(), f"{user_id}|{expiry}".encode(), "sha256").hexdigest()
    if not hmac.compare_digest(good, sig) or int(expiry) < time.time():
        return None
    return user_id


def _fernet() -> Fernet:
    key = hashlib.sha256((os.getenv("TOKEN_ENCRYPTION_KEY") or "dev-only-key").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
