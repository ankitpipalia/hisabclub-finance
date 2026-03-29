"""Symmetric encryption helpers for sensitive persisted blobs."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from app.config import settings


def _derive_fernet_key() -> bytes:
    configured = (settings.data_encryption_key or "").strip()
    if configured:
        raw = configured.encode("utf-8")
        if len(raw) == 44:
            return raw
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)

    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    return Fernet(_derive_fernet_key())


def encrypt_json_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    token = _fernet().encrypt(encoded)
    return token.decode("utf-8")


def decrypt_json_payload(token: str) -> dict[str, Any]:
    # Backward compatibility for rows stored before encryption rollout.
    value = (token or "").strip()
    if value.startswith("{"):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Expected JSON object")

    decoded = _fernet().decrypt(value.encode("utf-8"))
    parsed = json.loads(decoded.decode("utf-8"))
    if isinstance(parsed, dict):
        return parsed
    raise ValueError("Expected JSON object")


def encrypt_text(value: str) -> str:
    token = _fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(token: str) -> str:
    decoded = _fernet().decrypt(token.encode("utf-8"))
    return decoded.decode("utf-8")
