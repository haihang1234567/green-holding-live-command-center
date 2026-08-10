"""Real TikTok adapter shell.

The application does NOT assume every metric or LIVE-status API exists.
Once TikTok approves the API package, configure the endpoint URLs and map the
approved response fields here. The rest of the app does not change.
"""
from typing import Any
import httpx
from app.core.config import get_settings
from app.providers.base import TikTokShopProvider, TikTokAdsProvider, TikTokLiveProvider


def _dotted(data: Any, path: str, default=None):
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


class _HttpBase:
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.Client(timeout=20.0)

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get(self, url: str | None, token: str | None, params: dict | None = None) -> dict:
        if not url:
            return {"data": None, "optional": True, "reason": "Endpoint not configured"}
        response = self.client.get(url, headers=self._headers(token), params=params or {})
        response.raise_for_status()
        return response.json()


class RealTikTokShopProvider(_HttpBase, TikTokShopProvider):
    def get_orders(self, channel_external_id: str | None, since_iso: str | None = None) -> list[dict]:
        raw = self._get(
            self.settings.tiktok_shop_orders_url,
            self.settings.tiktok_shop_access_token,
            {"channel_id": channel_external_id, "since": since_iso} if channel_external_id else {"since": since_iso},
        )
        rows = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return []
        mapped = []
        for row in rows:
            mapped.append({
                "order_id": _dotted(row, self.settings.map_order_id),
                "amount": _dotted(row, self.settings.map_order_amount, 0),
                "status": _dotted(row, self.settings.map_order_status, "UNKNOWN"),
                "product_id": _dotted(row, self.settings.map_product_id),
                "sku_id": _dotted(row, self.settings.map_sku_id),
                "raw": row,
            })
        return mapped

    def get_products(self, channel_external_id: str | None) -> list[dict]:
        raw = self._get(self.settings.tiktok_shop_products_url, self.settings.tiktok_shop_access_token, {"channel_id": channel_external_id} if channel_external_id else None)
        rows = raw.get("data") if isinstance(raw, dict) else None
        return rows if isinstance(rows, list) else []

    def get_refunds(self, channel_external_id: str | None, since_iso: str | None = None) -> list[dict]:
        raw = self._get(self.settings.tiktok_shop_refunds_url, self.settings.tiktok_shop_access_token, {"channel_id": channel_external_id, "since": since_iso})
        rows = raw.get("data") if isinstance(raw, dict) else None
        return rows if isinstance(rows, list) else []


class RealTikTokAdsProvider(_HttpBase, TikTokAdsProvider):
    def get_metrics(self, advertiser_id: str | None, since_iso: str | None = None) -> dict:
        raw = self._get(self.settings.tiktok_ads_metrics_url, self.settings.tiktok_ads_access_token, {"advertiser_id": advertiser_id, "since": since_iso})
        return raw.get("data", {}) if isinstance(raw, dict) else {}


class RealTikTokLiveProvider(_HttpBase, TikTokLiveProvider):
    def get_live_status(self, channel_external_id: str | None) -> str:
        raw = self._get(self.settings.tiktok_live_status_url, self.settings.tiktok_shop_access_token, {"channel_id": channel_external_id})
        if raw.get("optional"):
            return "UNKNOWN"
        status = _dotted(raw, self.settings.map_live_status, "UNKNOWN")
        status = str(status).upper()
        return status if status in {"LIVE", "OFFLINE"} else "UNKNOWN"
