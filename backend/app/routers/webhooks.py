from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from ..config import get_settings
from ..database import SessionLocal
from ..models import Channel, LiveSession, SessionStatus, WebhookEvent
from ..realtime import manager
from ..services import sync_session_external

settings = get_settings()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_tiktok_shop_webhook(raw_body: bytes, authorization: str | None) -> bool:
    if not settings.tiktok_shop_app_key or not settings.tiktok_shop_app_secret:
        return settings.environment.lower() != "production"
    if not authorization:
        return False
    base = settings.tiktok_shop_app_key.encode("utf-8") + raw_body
    expected = hmac.new(settings.tiktok_shop_app_secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), authorization.strip().lower())


@router.post("/tiktok-shop")
async def tiktok_shop(request: Request):
    raw = await request.body()
    authorization = request.headers.get("Authorization")
    if not verify_tiktok_shop_webhook(raw, authorization):
        raise HTTPException(status_code=401, detail="Webhook signature không hợp lệ")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Payload không phải JSON") from exc

    event_key = str(payload.get("tts_notification_id") or payload.get("notification_id") or hashlib.sha256(raw).hexdigest())
    event_type = str(payload.get("event_type") or payload.get("type") or "UNKNOWN")
    shop_id = str(payload.get("shop_id") or "")
    active_session_id: int | None = None
    with SessionLocal() as db:
        if db.scalar(select(WebhookEvent.id).where(WebhookEvent.event_key == event_key)):
            return Response(status_code=200)
        db.add(WebhookEvent(event_key=event_key, source="TIKTOK_SHOP", event_type=event_type, payload_json=raw.decode("utf-8"), processed=False))
        if shop_id:
            channel = db.scalar(select(Channel).where(Channel.id.in_(settings.active_channel_ids),Channel.tiktok_shop_id == shop_id))
            if channel:
                active_session_id = db.scalar(select(LiveSession.id).where(LiveSession.channel_id == channel.id, LiveSession.status == SessionStatus.LIVE.value))
        db.commit()
    await manager.broadcast("webhook.received", {"source": "TIKTOK_SHOP", "event_type": event_type})
    # Webhook is an accelerator; scheduled polling remains the source-of-truth fallback.
    if active_session_id and settings.data_provider.upper() == "TIKTOK":
        asyncio.create_task(sync_session_external(active_session_id))
    return Response(status_code=200)


@router.post("/tiktok-live")
async def tiktok_live(request: Request):
    # Kept as a generic landing endpoint for a future/allowlisted LIVE webhook.
    # We store/broadcast the event without assuming an undocumented payload contract.
    raw = await request.body()
    event_key = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    with SessionLocal() as db:
        if not db.scalar(select(WebhookEvent.id).where(WebhookEvent.event_key == event_key)):
            db.add(WebhookEvent(event_key=event_key, source="TIKTOK_LIVE", event_type=str(payload.get("event") or "UNKNOWN"), payload_json=json.dumps(payload, ensure_ascii=False), processed=False))
            db.commit()
    await manager.broadcast("webhook.received", {"source": "TIKTOK_LIVE", "event": payload.get("event")})
    return Response(status_code=200)
