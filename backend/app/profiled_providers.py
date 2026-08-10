from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import httpx

from .config import Settings
from .models import Channel
from .providers import (
    AdsProvider,
    LiveStatusProvider,
    ShopProvider,
    TikTokAdsProvider,
    TikTokShopProvider,
    _json_path,
)


@dataclass(frozen=True)
class ShopProfile:
    slot: int
    name: str
    channel_id: int
    shop_base_url: str
    auth_url: str
    app_key: str
    app_secret: str
    access_token: str
    refresh_token: str
    shop_cipher: str
    shop_id: str
    ads_base_url: str
    ads_app_id: str
    ads_secret: str
    ads_access_token: str
    advertiser_id: str
    live_status_url: str
    live_status_method: str
    live_status_auth_mode: str
    live_status_token: str
    live_status_channel_param: str
    live_status_json_path: str
    live_value: str
    offline_value: str
    live_source_key: str


def _value(settings: Settings, slot: int, field: str, fallback: str = "") -> str:
    value = getattr(settings, f"shop{slot}_{field}", "")
    return str(value or fallback or "")


def profile_for_channel(settings: Settings, channel: Channel) -> ShopProfile:
    if channel.id == settings.shop2_channel_id:
        slot = 2
    else:
        slot = 1
    return ShopProfile(
        slot=slot,
        name=_value(settings, slot, "name", f"SHOP {slot}"),
        channel_id=int(getattr(settings, f"shop{slot}_channel_id")),
        shop_base_url=_value(settings, slot, "shop_base_url", settings.tiktok_shop_base_url),
        auth_url=_value(settings, slot, "auth_url", settings.tiktok_shop_auth_url),
        app_key=_value(settings, slot, "app_key", settings.tiktok_shop_app_key),
        app_secret=_value(settings, slot, "app_secret", settings.tiktok_shop_app_secret),
        access_token=_value(settings, slot, "access_token", settings.tiktok_shop_access_token),
        refresh_token=_value(settings, slot, "refresh_token", settings.tiktok_shop_refresh_token),
        shop_cipher=_value(settings, slot, "shop_cipher", channel.shop_cipher or ""),
        shop_id=_value(settings, slot, "shop_id", channel.tiktok_shop_id or ""),
        ads_base_url=_value(settings, slot, "ads_base_url", settings.tiktok_ads_base_url),
        ads_app_id=_value(settings, slot, "ads_app_id", settings.tiktok_ads_app_id),
        ads_secret=_value(settings, slot, "ads_secret", settings.tiktok_ads_secret),
        ads_access_token=_value(settings, slot, "ads_access_token", settings.tiktok_ads_access_token),
        advertiser_id=_value(settings, slot, "advertiser_id", channel.advertiser_id or ""),
        live_status_url=_value(settings, slot, "live_status_url"),
        live_status_method=_value(settings, slot, "live_status_method", "GET"),
        live_status_auth_mode=_value(settings, slot, "live_status_auth_mode", "BEARER").upper(),
        live_status_token=_value(settings, slot, "live_status_token"),
        live_status_channel_param=_value(settings, slot, "live_status_channel_param", "channel_id"),
        live_status_json_path=_value(settings, slot, "live_status_json_path", "data.status"),
        live_value=_value(settings, slot, "live_value", "LIVE"),
        offline_value=_value(settings, slot, "offline_value", "OFFLINE"),
        live_source_key=_value(settings, slot, "live_source_key", channel.live_source_key or ""),
    )


def apply_profile_to_channel(channel: Channel, profile: ShopProfile) -> None:
    # Non-secret identifiers may safely be persisted by normal SQLAlchemy commits.
    if profile.shop_cipher and not channel.shop_cipher:
        channel.shop_cipher = profile.shop_cipher
    if profile.shop_id and not channel.tiktok_shop_id:
        channel.tiktok_shop_id = profile.shop_id
    if profile.advertiser_id and not channel.advertiser_id:
        channel.advertiser_id = profile.advertiser_id
    if profile.live_source_key and not channel.live_source_key:
        channel.live_source_key = profile.live_source_key


def _shop_settings(base: Settings, p: ShopProfile) -> Settings:
    return Settings(
        tiktok_shop_base_url=p.shop_base_url,
        tiktok_shop_auth_url=p.auth_url,
        tiktok_shop_app_key=p.app_key,
        tiktok_shop_app_secret=p.app_secret,
        tiktok_shop_access_token=p.access_token,
        tiktok_shop_refresh_token=p.refresh_token,
        tiktok_shop_access_tokens_json="{}",
        tiktok_shop_refresh_tokens_json="{}",
    )


def _ads_settings(base: Settings, p: ShopProfile) -> Settings:
    return Settings(
        tiktok_ads_base_url=p.ads_base_url,
        tiktok_ads_app_id=p.ads_app_id,
        tiktok_ads_secret=p.ads_secret,
        tiktok_ads_access_token=p.ads_access_token,
        tiktok_ads_metrics=base.tiktok_ads_metrics,
        tiktok_ads_revenue_metric=base.tiktok_ads_revenue_metric,
        tiktok_ads_roas_metric=base.tiktok_ads_roas_metric,
    )


class DualTikTokShopProvider(ShopProvider):
    """Routes every Shop API call to the credential set belonging to that channel."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._providers: dict[int, TikTokShopProvider] = {}

    def provider_for(self, channel: Channel) -> tuple[TikTokShopProvider, ShopProfile]:
        p = profile_for_channel(self.settings, channel)
        apply_profile_to_channel(channel, p)
        if p.slot not in self._providers:
            self._providers[p.slot] = TikTokShopProvider(_shop_settings(self.settings, p))
        return self._providers[p.slot], p

    async def get_orders(self, channel: Channel, start: datetime, end: datetime):
        provider, _ = self.provider_for(channel)
        return await provider.get_orders(channel, start, end)

    async def get_returns(self, channel: Channel, start: datetime, end: datetime):
        provider, _ = self.provider_for(channel)
        return await provider.get_returns(channel, start, end)

    def normalize_order(self, raw):
        return TikTokShopProvider.normalize_order(raw)

    def normalize_return(self, raw):
        return TikTokShopProvider.normalize_return(raw)

    async def get_authorized_shops_for_channel(self, channel: Channel):
        provider, _ = self.provider_for(channel)
        return await provider.get_authorized_shops()


class DualTikTokAdsProvider(AdsProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._providers: dict[int, TikTokAdsProvider] = {}

    async def get_metrics(self, channel: Channel, start: datetime, end: datetime):
        p = profile_for_channel(self.settings, channel)
        apply_profile_to_channel(channel, p)
        if p.slot not in self._providers:
            self._providers[p.slot] = TikTokAdsProvider(_ads_settings(self.settings, p))
        return await self._providers[p.slot].get_metrics(channel, start, end)


class DualLiveStatusProvider(LiveStatusProvider):
    """Automatic detector for two independent shops.

    Each shop can use its own LIVE-status endpoint, token, JSON path and expected values.
    If TikTok gives a signed Shop Open API endpoint, set AUTH_MODE=TIKTOK_SHOP.
    Otherwise BEARER/NONE supports a partner/middleware status endpoint without code changes.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.shop = DualTikTokShopProvider(settings)

    async def get_channel_status(self, channel: Channel) -> str | None:
        p = profile_for_channel(self.settings, channel)
        apply_profile_to_channel(channel, p)
        if not p.live_status_url:
            return None

        source_key = p.live_source_key or channel.live_source_key or p.shop_id or p.shop_cipher or channel.handle or str(channel.id)
        params = {p.live_status_channel_param: source_key} if p.live_status_channel_param else {}
        auth_mode = p.live_status_auth_mode.upper()

        if auth_mode == "TIKTOK_SHOP":
            provider, _ = self.shop.provider_for(channel)
            parsed = urlparse(p.live_status_url)
            path = parsed.path or p.live_status_url
            payload = await provider._request(p.live_status_method, path, channel, query=params)
        else:
            headers: dict[str, str] = {}
            token = p.live_status_token or p.access_token
            if auth_mode == "BEARER" and token:
                headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.request(p.live_status_method.upper(), p.live_status_url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()

        value = _json_path(payload, p.live_status_json_path)
        text = str(value).strip().upper()
        if text == p.live_value.upper():
            return "LIVE"
        if text == p.offline_value.upper():
            return "OFFLINE"
        return None
