from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_secret(value: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${derived.hex()}"


def lookup_secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_secret(value: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        salt, digest = encoded.split("$", 1)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return secrets.compare_digest(derived.hex(), digest)


def issue_plain_secret(bytes_length: int = 32) -> str:
    return secrets.token_urlsafe(bytes_length)


def session_expiry(hours: int) -> datetime:
    return utcnow() + timedelta(hours=hours)


def dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def loads_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback
