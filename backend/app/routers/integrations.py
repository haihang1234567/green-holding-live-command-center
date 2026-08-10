from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Channel
from ..profiled_providers import DualTikTokShopProvider, profile_for_channel
from ..providers import TikTokAdsProvider, TikTokShopProvider, providers
from ..security import require_admin
from ..services import sync_session_external

settings = get_settings()
router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/status")
def status(db: Session = Depends(get_db), _=Depends(require_admin)):
    channels = db.scalars(select(Channel).order_by(Channel.id)).all()
    profiles = []
    for channel in channels:
        p = profile_for_channel(settings, channel)
        profiles.append({
            "slot": p.slot,
            "name": p.name,
            "channel_id": channel.id,
            "channel_name": channel.name,
            "handle": channel.handle,
            "shop": {
                "app_key": bool(p.app_key),
                "app_secret": bool(p.app_secret),
                "access_token": bool(p.access_token),
                "refresh_token": bool(p.refresh_token),
                "shop_cipher": bool(p.shop_cipher or channel.shop_cipher),
                "shop_id": p.shop_id or channel.tiktok_shop_id,
            },
            "ads": {
                "app_id": bool(p.ads_app_id),
                "secret": bool(p.ads_secret),
                "access_token": bool(p.ads_access_token),
                "advertiser_id": p.advertiser_id or channel.advertiser_id,
            },
            "live": {
                "endpoint_configured": bool(p.live_status_url),
                "auth_mode": p.live_status_auth_mode,
                "source_key": p.live_source_key or channel.live_source_key,
                "json_path": p.live_status_json_path,
            },
        })
    return {
        "data_provider": settings.data_provider.upper(),
        "live_status_provider": settings.live_status_provider.upper(),
        "polling_interval_seconds": settings.polling_interval_seconds,
        "metric_snapshot_interval_seconds": settings.metric_snapshot_interval_seconds,
        "profiles": profiles,
        "ads_metrics": [x.strip() for x in settings.tiktok_ads_metrics.split(",") if x.strip()],
        "revenue_metric": settings.tiktok_ads_revenue_metric or None,
        "roas_metric": settings.tiktok_ads_roas_metric or None,
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


@router.post("/test/shop/{channel_id}")
async def test_shop_channel(channel_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Không tìm thấy kênh")
    if not isinstance(providers.shop, DualTikTokShopProvider):
        raise HTTPException(409, "Hệ thống chưa chạy chế độ 2 Shop TIKTOK")
    try:
        shops = await providers.shop.get_authorized_shops_for_channel(channel)
        return {"ok": True, "channel_id": channel_id, "shops": shops}
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
