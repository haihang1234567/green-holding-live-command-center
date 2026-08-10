from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/status")
def status():
    s = get_settings()
    return {"provider": s.data_provider.upper(), "database": "POSTGRESQL" if s.database_url.startswith("postgres") else "SQLITE", "poll_interval_seconds": s.poll_interval_seconds, "tiktok": {"shop_credentials": bool(s.tiktok_shop_app_key and s.tiktok_shop_app_secret and s.tiktok_shop_access_token), "ads_credentials": bool(s.tiktok_ads_app_id and s.tiktok_ads_secret and s.tiktok_ads_access_token), "orders_endpoint": bool(s.tiktok_shop_orders_url), "ads_endpoint": bool(s.tiktok_ads_metrics_url), "live_status_endpoint": bool(s.tiktok_live_status_url)}, "note": "Các metric TikTok không được API cung cấp sẽ trả về Chưa có dữ liệu thay vì làm ứng dụng lỗi."}
