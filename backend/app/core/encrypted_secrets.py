from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import get_settings

SETTINGS_ENC_KEY_MISSING_DETAIL = (
    "SETTINGS_ENC_KEY is required for encrypted settings and delegated secret material."
)
SETTINGS_ENC_KEY_DECRYPT_DETAIL = (
    "Stored secret could not be decrypted with the current SETTINGS_ENC_KEY. "
    "Keep the previous key or re-enter the affected secret."
)


def _fernet() -> Fernet:
    settings = get_settings()
    source = settings.settings_enc_key.strip()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SETTINGS_ENC_KEY_MISSING_DETAIL,
        )
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=SETTINGS_ENC_KEY_DECRYPT_DETAIL,
        ) from exc
