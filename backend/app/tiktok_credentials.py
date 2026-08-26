from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal
from .models import AppSetting


settings = get_settings()
_PREFIX = "tiktok_shop_credentials:"
_PENDING_PREFIX = "tiktok_shop_pending:"


def _credential_key(shop_cipher: str) -> str:
    digest = hashlib.sha256(shop_cipher.encode("utf-8")).hexdigest()
    return f"{_PREFIX}{digest}"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""


def _upsert(key: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as db:
        row = db.get(AppSetting, key)
        value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()


def _load(key: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        row = db.get(AppSetting, key)
        if not row:
            return None
        try:
            payload = json.loads(row.value)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    payload["access_token"] = _decrypt(str(payload.pop("access_token_encrypted", "")))
    payload["refresh_token"] = _decrypt(str(payload.pop("refresh_token_encrypted", "")))
    return payload


def _payload(
    *,
    access_token: str,
    refresh_token: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_metadata = {
        key: value
        for key, value in (metadata or {}).items()
        if key not in {"access_token", "refresh_token", "app_secret"}
    }
    return {
        **safe_metadata,
        "access_token_encrypted": _encrypt(access_token),
        "refresh_token_encrypted": _encrypt(refresh_token),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def store_pending_authorization(
    identifier: str,
    *,
    access_token: str,
    refresh_token: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    safe_identifier = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:24]
    key = f"{_PENDING_PREFIX}{safe_identifier}"
    _upsert(key, _payload(access_token=access_token, refresh_token=refresh_token, metadata=metadata))
    return key


def delete_pending_authorization(key: str) -> None:
    if not key.startswith(_PENDING_PREFIX):
        return
    with SessionLocal() as db:
        row = db.get(AppSetting, key)
        if row:
            db.delete(row)
            db.commit()


def store_shop_authorization(
    shop_cipher: str,
    *,
    access_token: str,
    refresh_token: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not shop_cipher:
        raise ValueError("shop_cipher is required")
    _upsert(
        _credential_key(shop_cipher),
        _payload(
            access_token=access_token,
            refresh_token=refresh_token,
            metadata={"shop_cipher": shop_cipher, **(metadata or {})},
        ),
    )


def load_shop_authorization(shop_cipher: str) -> dict[str, Any] | None:
    if not shop_cipher:
        return None
    return _load(_credential_key(shop_cipher))


def update_shop_tokens(shop_cipher: str, access_token: str, refresh_token: str) -> None:
    current = load_shop_authorization(shop_cipher) or {}
    metadata = {
        key: value
        for key, value in current.items()
        if key not in {"access_token", "refresh_token", "updated_at"}
    }
    store_shop_authorization(
        shop_cipher,
        access_token=access_token,
        refresh_token=refresh_token,
        metadata=metadata,
    )


def has_shop_authorization(shop_cipher: str) -> bool:
    if not shop_cipher:
        return False
    with SessionLocal() as db:
        return bool(db.scalar(select(AppSetting.key).where(AppSetting.key == _credential_key(shop_cipher))))
