from __future__ import annotations

import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import Settings, get_settings
from .models import Channel


def _money(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, dict):
        value = value.get("amount") or value.get("value") or 0
    text = str(value).strip().replace(",", "")
    # Some APIs may return strings with a currency prefix. Keep only numeric chars/dot/minus.
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
    try:
        return float(Decimal(cleaned or "0"))
    except (InvalidOperation, ValueError):
        return 0.0


def _epoch_to_dt(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _json_path(data: Any, path: str) -> Any:
    current = data
    for token in [x for x in path.split(".") if x]:
        if isinstance(current, dict):
            current = current.get(token)
        elif isinstance(current, list) and token.isdigit():
            idx = int(token)
            current = current[idx] if 0 <= idx < len(current) else None
        else:
            return None
    return current


class LiveStatusProvider(ABC):
    @abstractmethod
    async def get_channel_status(self, channel: Channel) -> str | None:
        """Return LIVE/OFFLINE or None when status is unavailable."""


class ShopProvider(ABC):
    @abstractmethod
    async def get_orders(self, channel: Channel, start: datetime, end: datetime) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def get_returns(self, channel: Channel, start: datetime, end: datetime) -> list[dict[str, Any]]:
        pass


class AdsProvider(ABC):
    @abstractmethod
    async def get_metrics(self, channel: Channel, start: datetime, end: datetime) -> dict[str, Any]:
        pass


class MockLiveProvider(LiveStatusProvider):
    async def get_channel_status(self, channel: Channel) -> str | None:
        return "LIVE" if channel.mock_is_live else "OFFLINE"


class ManualLiveProvider(LiveStatusProvider):
    async def get_channel_status(self, channel: Channel) -> str | None:
        return None


class EndpointLiveProvider(LiveStatusProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_channel_status(self, channel: Channel) -> str | None:
        if not self.settings.tiktok_live_status_url:
            return None
        params = {self.settings.tiktok_live_status_channel_param: channel.live_source_key or channel.handle or str(channel.id)}
        headers: dict[str, str] = {}
        if self.settings.tiktok_live_status_token:
            headers["Authorization"] = f"Bearer {self.settings.tiktok_live_status_token}"
        async with httpx.AsyncClient(timeout=12) as client:
            method = self.settings.tiktok_live_status_method.upper()
            response = await client.request(method, self.settings.tiktok_live_status_url, params=params, headers=headers)
            response.raise_for_status()
            value = _json_path(response.json(), self.settings.tiktok_live_status_json_path)
        if str(value).upper() == self.settings.tiktok_live_value.upper():
            return "LIVE"
        if str(value).upper() == self.settings.tiktok_offline_value.upper():
            return "OFFLINE"
        return None


class MockShopProvider(ShopProvider):
    async def get_orders(self, channel: Channel, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return []

    async def get_returns(self, channel: Channel, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return []


class MockAdsProvider(AdsProvider):
    async def get_metrics(self, channel: Channel, start: datetime, end: datetime) -> dict[str, Any]:
        return {}


class TikTokShopProvider(ShopProvider):
    """TikTok Shop Open API adapter.

    The signature follows TikTok Shop's documented HMAC-SHA256 signing algorithm.
    Tokens remain backend-only. A per-shop token JSON map is supported for the two-shop setup.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._token_override: dict[str, str] = {}
        self._refresh_override: dict[str, str] = {}

    def _token_for(self, shop_cipher: str) -> str:
        return (
            self._token_override.get(shop_cipher)
            or self.settings.shop_access_tokens.get(shop_cipher)
            or self.settings.tiktok_shop_access_token
        )

    def _refresh_for(self, shop_cipher: str) -> str:
        return (
            self._refresh_override.get(shop_cipher)
            or self.settings.shop_refresh_tokens.get(shop_cipher)
            or self.settings.tiktok_shop_refresh_token
        )

    @staticmethod
    def _body_string(body: dict[str, Any] | None) -> str:
        if not body:
            return ""
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    def generate_sign(self, path: str, params: dict[str, Any], body_string: str = "", content_type: str = "application/json") -> str:
        filtered = {k: v for k, v in params.items() if k not in {"sign", "access_token"} and v is not None}
        param_string = "".join(f"{key}{filtered[key]}" for key in sorted(filtered))
        sign_string = f"{path}{param_string}"
        if content_type.lower() != "multipart/form-data" and body_string:
            sign_string += body_string
        wrapped = f"{self.settings.tiktok_shop_app_secret}{sign_string}{self.settings.tiktok_shop_app_secret}"
        return hmac.new(
            self.settings.tiktok_shop_app_secret.encode("utf-8"),
            wrapped.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _refresh_access_token(self, shop_cipher: str) -> bool:
        refresh_token = self._refresh_for(shop_cipher)
        if not (refresh_token and self.settings.tiktok_shop_app_key and self.settings.tiktok_shop_app_secret):
            return False
        params = {
            "app_key": self.settings.tiktok_shop_app_key,
            "app_secret": self.settings.tiktok_shop_app_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{self.settings.tiktok_shop_auth_url}/token/refresh", params=params)
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data", payload)
        if payload.get("code", 0) not in (0, None) or not data.get("access_token"):
            return False
        self._token_override[shop_cipher] = data["access_token"]
        if data.get("refresh_token"):
            self._refresh_override[shop_cipher] = data["refresh_token"]
        return True

    async def _request(
        self,
        method: str,
        path: str,
        channel: Channel,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        if not self.settings.tiktok_shop_app_key or not self.settings.tiktok_shop_app_secret:
            raise RuntimeError("Thiếu TIKTOK_SHOP_APP_KEY / TIKTOK_SHOP_APP_SECRET")
        if not channel.shop_cipher:
            raise RuntimeError(f"Kênh {channel.name} chưa có shop_cipher")
        token = self._token_for(channel.shop_cipher)
        if not token:
            raise RuntimeError(f"Kênh {channel.name} chưa có TikTok Shop access token")

        params: dict[str, Any] = {
            "app_key": self.settings.tiktok_shop_app_key,
            "timestamp": int(time.time()),
            "shop_cipher": channel.shop_cipher,
            **(query or {}),
        }
        params = {k: v for k, v in params.items() if v is not None and v != ""}
        body_string = self._body_string(body)
        params["sign"] = self.generate_sign(path, params, body_string)
        headers = {"content-type": "application/json", "x-tts-access-token": token}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method.upper(),
                f"{self.settings.tiktok_shop_base_url}{path}",
                params=params,
                headers=headers,
                content=body_string.encode("utf-8") if body_string else None,
            )
        # If a token expired, refresh once and retry with a newly generated timestamp/signature.
        if response.status_code in {401, 403} and retry_auth and await self._refresh_access_token(channel.shop_cipher):
            return await self._request(method, path, channel, query=query, body=body, retry_auth=False)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (0, None):
            message = payload.get("message") or "TikTok Shop API error"
            if retry_auth and any(word in str(message).lower() for word in ("token", "auth")):
                if await self._refresh_access_token(channel.shop_cipher):
                    return await self._request(method, path, channel, query=query, body=body, retry_auth=False)
            raise RuntimeError(f"TikTok Shop API: {payload.get('code')} - {message}")
        return payload

    async def get_authorized_shops(self, token_shop_cipher: str = "") -> list[dict[str, Any]]:
        # Special request without shop_cipher. Uses global token.
        token = self.settings.tiktok_shop_access_token
        if not token:
            raise RuntimeError("Thiếu TIKTOK_SHOP_ACCESS_TOKEN")
        path = "/authorization/202309/shops"
        params: dict[str, Any] = {"app_key": self.settings.tiktok_shop_app_key, "timestamp": int(time.time())}
        params["sign"] = self.generate_sign(path, params)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.settings.tiktok_shop_base_url}{path}",
                params=params,
                headers={"content-type": "application/json", "x-tts-access-token": token},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") not in (0, None):
            raise RuntimeError(payload.get("message") or "Không lấy được authorized shops")
        data = payload.get("data") or {}
        return data.get("shops") or data.get("shop_list") or []

    async def get_orders(self, channel: Channel, start: datetime, end: datetime) -> list[dict[str, Any]]:
        path = "/order/202309/orders/search"
        page_token: str | None = None
        output: list[dict[str, Any]] = []
        for _ in range(10):
            query = {"page_size": 100, "sort_field": "update_time", "sort_order": "ASC", "page_token": page_token}
            body = {"update_time_ge": int(start.timestamp()), "update_time_lt": int(end.timestamp()) + 1}
            payload = await self._request("POST", path, channel, query=query, body=body)
            data = payload.get("data") or {}
            output.extend(data.get("orders") or [])
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return output

    async def get_returns(self, channel: Channel, start: datetime, end: datetime) -> list[dict[str, Any]]:
        path = "/return_refund/202309/returns/search"
        page_token: str | None = None
        output: list[dict[str, Any]] = []
        for _ in range(10):
            query = {"page_size": 50, "sort_field": "update_time", "sort_order": "ASC", "page_token": page_token}
            body = {"update_time_ge": int(start.timestamp()), "update_time_lt": int(end.timestamp()) + 1}
            payload = await self._request("POST", path, channel, query=query, body=body)
            data = payload.get("data") or {}
            output.extend(data.get("returns") or data.get("return_orders") or [])
            page_token = data.get("next_page_token")
            if not page_token:
                break
        return output

    @staticmethod
    def normalize_order(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize an order into one or more SKU-level records.

        TikTok response shapes can evolve. We intentionally accept several field aliases and keep raw JSON,
        so a new/optional field never crashes the dashboard.
        """
        order_id = str(raw.get("id") or raw.get("order_id") or "")
        created_at = _epoch_to_dt(raw.get("create_time") or raw.get("created_at"))
        updated_at = _epoch_to_dt(raw.get("update_time") or raw.get("updated_at") or raw.get("create_time"))
        status = str(raw.get("status") or raw.get("order_status") or "UNKNOWN")
        payment = raw.get("payment") or raw.get("payment_info") or {}
        order_total = _money(
            raw.get("payment_amount")
            or payment.get("total_amount")
            or payment.get("total_payment")
            or raw.get("total_amount")
        )
        items = raw.get("line_items") or raw.get("items") or raw.get("skus") or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            return [{
                "order_id": order_id,
                "created_at": created_at,
                "updated_at": updated_at,
                "sku_id": "",
                "product_id": "",
                "product_name": "",
                "quantity": 1,
                "amount": order_total,
                "payment_amount": order_total,
                "currency": payment.get("currency") or raw.get("currency") or "VND",
                "order_status": status,
            }]
        rows: list[dict[str, Any]] = []
        item_total = sum(max(1, int(x.get("quantity") or 1)) for x in items)
        for item in items:
            qty = max(1, int(item.get("quantity") or 1))
            sale_price = _money(item.get("sale_price") or item.get("price") or item.get("sku_sale_price"))
            amount = sale_price * qty if sale_price else (order_total * qty / item_total if item_total else order_total)
            rows.append({
                "order_id": order_id if len(items) == 1 else f"{order_id}:{item.get('id') or item.get('sku_id') or len(rows)+1}",
                "parent_order_id": order_id,
                "created_at": created_at,
                "updated_at": updated_at,
                "sku_id": str(item.get("sku_id") or item.get("id") or ""),
                "product_id": str(item.get("product_id") or ""),
                "product_name": str(item.get("product_name") or item.get("display_name") or item.get("name") or ""),
                "quantity": qty,
                "amount": amount,
                "payment_amount": amount,
                "currency": (item.get("price") or {}).get("currency") if isinstance(item.get("price"), dict) else payment.get("currency") or raw.get("currency") or "VND",
                "order_status": status,
            })
        return rows

    @staticmethod
    def normalize_return(raw: dict[str, Any]) -> dict[str, Any]:
        order_id = str(raw.get("order_id") or raw.get("order", {}).get("id") or "")
        refund_amount = _money(raw.get("refund_amount") or raw.get("refund_total") or raw.get("refund") or 0)
        status = str(raw.get("return_status") or raw.get("status") or "")
        return {
            "order_id": order_id,
            "refund_amount": refund_amount,
            "status": status,
            "updated_at": _epoch_to_dt(raw.get("update_time") or raw.get("create_time")),
            "raw": raw,
        }


class TikTokAdsProvider(AdsProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_metrics(self, channel: Channel, start: datetime, end: datetime) -> dict[str, Any]:
        if not channel.advertiser_id:
            return {}
        if not self.settings.tiktok_ads_access_token:
            raise RuntimeError("Thiếu TIKTOK_ADS_ACCESS_TOKEN")
        metrics = [m.strip() for m in self.settings.tiktok_ads_metrics.split(",") if m.strip()]
        for optional in (self.settings.tiktok_ads_revenue_metric, self.settings.tiktok_ads_roas_metric):
            if optional and optional not in metrics:
                metrics.append(optional)
        params = {
            "advertiser_id": channel.advertiser_id,
            "report_type": "BASIC",
            "data_level": "AUCTION_ADVERTISER",
            "dimensions": json.dumps(["stat_time_hour"]),
            "metrics": json.dumps(metrics),
            "start_date": start.astimezone(timezone.utc).date().isoformat(),
            "end_date": end.astimezone(timezone.utc).date().isoformat(),
            "page": 1,
            "page_size": 1000,
        }
        headers = {"Access-Token": self.settings.tiktok_ads_access_token}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.settings.tiktok_ads_base_url}/report/integrated/get/", params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        if payload.get("code") not in (0, None):
            raise RuntimeError(f"TikTok Ads API: {payload.get('code')} - {payload.get('message')}")
        rows = ((payload.get("data") or {}).get("list") or [])
        totals = {"spend": 0.0, "impressions": 0, "clicks": 0, "orders": 0, "gross_revenue": 0.0, "roas": 0.0}
        relevant_rows = 0
        for row in rows:
            dimensions = row.get("dimensions") or {}
            hour_text = dimensions.get("stat_time_hour")
            if hour_text:
                try:
                    row_time = datetime.fromisoformat(str(hour_text).replace("Z", "+00:00"))
                    if row_time.tzinfo is None:
                        row_time = row_time.replace(tzinfo=timezone.utc)
                    if row_time < start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0) or row_time > end.astimezone(timezone.utc):
                        continue
                except Exception:
                    pass
            relevant_rows += 1
            m = row.get("metrics") or {}
            totals["spend"] += _money(m.get("spend"))
            totals["impressions"] += int(float(m.get("impressions") or 0))
            totals["clicks"] += int(float(m.get("clicks") or 0))
            totals["orders"] += int(float(m.get("conversion") or m.get("conversions") or 0))
            if self.settings.tiktok_ads_revenue_metric:
                totals["gross_revenue"] += _money(m.get(self.settings.tiktok_ads_revenue_metric))
        if self.settings.tiktok_ads_roas_metric and rows:
            roas_values = [_money((r.get("metrics") or {}).get(self.settings.tiktok_ads_roas_metric)) for r in rows]
            roas_values = [x for x in roas_values if x]
            if roas_values:
                totals["roas"] = sum(roas_values) / len(roas_values)
        elif totals["spend"] and totals["gross_revenue"]:
            totals["roas"] = totals["gross_revenue"] / totals["spend"]
        totals["rows"] = relevant_rows
        return totals


class ProviderBundle:
    def __init__(self, settings: Settings | None = None):
        settings = settings or get_settings()
        self.settings = settings
        if settings.data_provider.upper() == "TIKTOK":
            self.shop: ShopProvider = TikTokShopProvider(settings)
            self.ads: AdsProvider = TikTokAdsProvider(settings)
        else:
            self.shop = MockShopProvider()
            self.ads = MockAdsProvider()

        live_mode = settings.live_status_provider.upper()
        if live_mode == "TIKTOK_ENDPOINT":
            self.live: LiveStatusProvider = EndpointLiveProvider(settings)
        elif live_mode == "MANUAL":
            self.live = ManualLiveProvider()
        else:
            self.live = MockLiveProvider()


providers = ProviderBundle()
