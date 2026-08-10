from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Channel
from ..providers import TikTokAdsProvider, TikTokShopProvider, providers
from ..security import require_admin
from ..services import sync_session_external

settings = get_settings()
router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(require_admin)):
    channels = db.scalars(select(Channel).order_by(Channel.id)).all()
    return {
        "data_provider": settings.data_provider.upper(),
        "live_status_provider": settings.live_status_provider.upper(),
        "shop": {
            "app_key": bool(settings.tiktok_shop_app_key),
            "app_secret": bool(settings.tiktok_shop_app_secret),
            "access_token": bool(settings.tiktok_shop_access_token or settings.shop_access_tokens),
            "refresh_token": bool(settings.tiktok_shop_refresh_token or settings.shop_refresh_tokens),
            "base_url": settings.tiktok_shop_base_url,
        },
        "ads": {
            "app_id": bool(settings.tiktok_ads_app_id),
            "secret": bool(settings.tiktok_ads_secret),
            "access_token": bool(settings.tiktok_ads_access_token),
            "base_url": settings.tiktok_ads_base_url,
            "metrics": [x.strip() for x in settings.tiktok_ads_metrics.split(",") if x.strip()],
            "revenue_metric": settings.tiktok_ads_revenue_metric or None,
            "roas_metric": settings.tiktok_ads_roas_metric or None,
        },
        "live": {
            "endpoint_configured": bool(settings.tiktok_live_status_url),
            "mode": settings.live_status_provider.upper(),
        },
        "channels": [{"id": x.id, "name": x.name, "shop_cipher": bool(x.shop_cipher), "shop_id": x.tiktok_shop_id, "advertiser_id": x.advertiser_id, "live_source_key": x.live_source_key} for x in channels],
    }


@router.post("/test/shop")
async def test_shop(_=Depends(require_admin)):
    if not isinstance(providers.shop, TikTokShopProvider):
        raise HTTPException(409, "DATA_PROVIDER chưa đặt thành TIKTOK")
    try:
        shops = await providers.shop.get_authorized_shops()
        return {"ok": True, "shops": shops}
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/test/ads/{channel_id}")
async def test_ads(channel_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Không tìm thấy kênh")
    if not isinstance(providers.ads, TikTokAdsProvider):
        raise HTTPException(409, "DATA_PROVIDER chưa đặt thành TIKTOK")
    try:
        end = datetime.now(timezone.utc)
        data = await providers.ads.get_metrics(channel, end - timedelta(hours=2), end)
        return {"ok": True, "data": data}
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/sync/{session_id}")
async def sync(session_id: int, _=Depends(require_admin)):
    try:
        return await sync_session_external(session_id)
    except Exception as exc:
        raise HTTPException(502, str(exc)) from exc
