from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import Settings, get_settings
from .models import Channel
from .providers import TikTokAdsProvider, TikTokShopProvider

settings = get_settings()


def _path(data: Any, dotted: str) -> Any:
    current = data
    for token in [x for x in (dotted or "").split(".") if x]:
        if isinstance(current, dict):
            current = current.get(token)
        elif isinstance(current, list) and token.isdigit():
            idx = int(token)
            current = current[idx] if 0 <= idx < len(current) else None
        else:
            return None
    return current


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("amount") or value.get("value")
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ShopProfile:
    slot: int
    channel_id: int
    name: str
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
    live_status_mode: str
    live_value: str
    offline_value: str
    live_source_key: str
    live_room_id_json_path: str
    live_metrics_url: str
    live_metrics_method: str
    live_metrics_auth_mode: str
    live_metrics_token: str
    live_metrics_room_param: str
    live_metric_paths: dict[str, str]


def _s(slot: int, name: str, fallback: str = "") -> str:
    return str(getattr(settings, f"shop{slot}_{name}", "") or fallback or "")


def profile_for_channel(channel: Channel) -> ShopProfile:
    slot = 2 if channel.id == settings.shop2_channel_id else 1
    paths_raw = _s(slot, "live_metric_paths_json", "{}")
    try:
        paths = json.loads(paths_raw)
        if not isinstance(paths, dict):
            paths = {}
    except json.JSONDecodeError:
        paths = {}
    return ShopProfile(
        slot=slot,
        channel_id=int(getattr(settings, f"shop{slot}_channel_id")),
        name=_s(slot, "name", f"SHOP {slot}"),
        shop_base_url=_s(slot, "shop_base_url", settings.tiktok_shop_base_url),
        auth_url=_s(slot, "auth_url", settings.tiktok_shop_auth_url),
        app_key=_s(slot, "app_key", settings.tiktok_shop_app_key),
        app_secret=_s(slot, "app_secret", settings.tiktok_shop_app_secret),
        access_token=_s(slot, "access_token", settings.tiktok_shop_access_token),
        refresh_token=_s(slot, "refresh_token", settings.tiktok_shop_refresh_token),
        shop_cipher=_s(slot, "shop_cipher", channel.shop_cipher or ""),
        shop_id=_s(slot, "shop_id", channel.tiktok_shop_id or ""),
        ads_base_url=_s(slot, "ads_base_url", settings.tiktok_ads_base_url),
        ads_app_id=_s(slot, "ads_app_id", settings.tiktok_ads_app_id),
        ads_secret=_s(slot, "ads_secret", settings.tiktok_ads_secret),
        ads_access_token=_s(slot, "ads_access_token", settings.tiktok_ads_access_token),
        advertiser_id=_s(slot, "advertiser_id", channel.advertiser_id or ""),
        live_status_url=_s(slot, "live_status_url"),
        live_status_method=_s(slot, "live_status_method", "GET").upper(),
        live_status_auth_mode=_s(slot, "live_status_auth_mode", "BEARER").upper(),
        live_status_token=_s(slot, "live_status_token"),
        live_status_channel_param=_s(slot, "live_status_channel_param", "channel_id"),
        live_status_json_path=_s(slot, "live_status_json_path", "data.status"),
        live_status_mode=_s(slot, "live_status_mode", "VALUE").upper(),
        live_value=_s(slot, "live_value", "LIVE"),
        offline_value=_s(slot, "offline_value", "OFFLINE"),
        live_source_key=_s(slot, "live_source_key", channel.live_source_key or ""),
        live_room_id_json_path=_s(slot, "live_room_id_json_path", "data.live_room_id"),
        live_metrics_url=_s(slot, "live_metrics_url"),
        live_metrics_method=_s(slot, "live_metrics_method", "GET").upper(),
        live_metrics_auth_mode=_s(slot, "live_metrics_auth_mode", "TIKTOK_SHOP").upper(),
        live_metrics_token=_s(slot, "live_metrics_token"),
        live_metrics_room_param=_s(slot, "live_metrics_room_param", "live_room_id"),
        live_metric_paths={str(k): str(v) for k, v in paths.items()},
    )


def apply_profile(channel: Channel, p: ShopProfile) -> None:
    if p.shop_cipher:
        channel.shop_cipher = p.shop_cipher
    if p.shop_id:
        channel.tiktok_shop_id = p.shop_id
    if p.advertiser_id:
        channel.advertiser_id = p.advertiser_id
    if p.live_source_key:
        channel.live_source_key = p.live_source_key


def _shop_settings(p: ShopProfile) -> Settings:
    return Settings(tiktok_shop_base_url=p.shop_base_url,tiktok_shop_auth_url=p.auth_url,tiktok_shop_app_key=p.app_key,tiktok_shop_app_secret=p.app_secret,tiktok_shop_access_token=p.access_token,tiktok_shop_refresh_token=p.refresh_token,tiktok_shop_access_tokens_json="{}",tiktok_shop_refresh_tokens_json="{}")


def _ads_settings(p: ShopProfile) -> Settings:
    return Settings(tiktok_ads_base_url=p.ads_base_url,tiktok_ads_app_id=p.ads_app_id,tiktok_ads_secret=p.ads_secret,tiktok_ads_access_token=p.ads_access_token,tiktok_ads_metrics=settings.tiktok_ads_metrics,tiktok_ads_revenue_metric=settings.tiktok_ads_revenue_metric,tiktok_ads_roas_metric=settings.tiktok_ads_roas_metric)


_shop_clients: dict[int, TikTokShopProvider] = {}
_ads_clients: dict[int, TikTokAdsProvider] = {}


def shop_client(channel: Channel) -> tuple[TikTokShopProvider, ShopProfile]:
    p = profile_for_channel(channel); apply_profile(channel, p)
    if p.slot not in _shop_clients: _shop_clients[p.slot] = TikTokShopProvider(_shop_settings(p))
    return _shop_clients[p.slot], p


def ads_client(channel: Channel) -> tuple[TikTokAdsProvider, ShopProfile]:
    p = profile_for_channel(channel); apply_profile(channel, p)
    if p.slot not in _ads_clients: _ads_clients[p.slot] = TikTokAdsProvider(_ads_settings(p))
    return _ads_clients[p.slot], p


async def _generic_request(*,url:str,method:str,auth_mode:str,token:str,params:dict[str,Any])->dict[str,Any]:
    headers: dict[str,str] = {}; mode=auth_mode.upper()
    if mode=="BEARER" and token: headers["Authorization"]=f"Bearer {token}"
    elif mode in {"X_TTS","X-TTS"} and token: headers["x-tts-access-token"]=token
    async with httpx.AsyncClient(timeout=25) as client:
        response=await client.request(method.upper(),url,params=params,headers=headers); response.raise_for_status(); payload=response.json()
    return payload if isinstance(payload,dict) else {"data":payload}


async def _profile_request(channel:Channel,*,url:str,method:str,auth_mode:str,token:str,params:dict[str,Any])->dict[str,Any]:
    if auth_mode.upper()=="TIKTOK_SHOP":
        client,_=shop_client(channel); parsed=urlparse(url); path=parsed.path if parsed.scheme else url
        return await client._request(method,path,channel,query=params)
    return await _generic_request(url=url,method=method,auth_mode=auth_mode,token=token,params=params)


async def get_live_signal(channel: Channel) -> dict[str, Any]:
    p=profile_for_channel(channel); apply_profile(channel,p)
    if settings.live_status_provider.upper()=="MOCK":
        return {"status":"LIVE" if channel.mock_is_live else "OFFLINE","live_room_id":None,"raw":{"mock":True}}
    if not p.live_status_url:
        return {"status":"UNKNOWN","live_room_id":None,"raw":{"reason":"live_status_url_missing"}}
    key=p.live_source_key or p.shop_id or p.shop_cipher or channel.handle or str(channel.id)
    params={p.live_status_channel_param:key} if p.live_status_channel_param else {}
    payload=await _profile_request(channel,url=p.live_status_url,method=p.live_status_method,auth_mode=p.live_status_auth_mode,token=p.live_status_token or p.access_token,params=params)
    value=_path(payload,p.live_status_json_path); room_id=_path(payload,p.live_room_id_json_path) if p.live_room_id_json_path else None
    if p.live_status_mode=="NONEMPTY": status="LIVE" if bool(value) else "OFFLINE"
    else:
        text=str(value).strip().upper(); status="LIVE" if text==p.live_value.upper() else "OFFLINE" if text==p.offline_value.upper() else "UNKNOWN"
    return {"status":status,"live_room_id":str(room_id) if room_id not in (None,"") else None,"raw":payload}


async def get_live_metrics(channel: Channel, live_room_id: str | None) -> dict[str, Any] | None:
    p=profile_for_channel(channel)
    if not p.live_metrics_url: return None
    key=live_room_id or p.live_source_key or p.shop_id or p.shop_cipher or channel.handle or str(channel.id)
    params={p.live_metrics_room_param:key} if p.live_metrics_room_param else {}
    payload=await _profile_request(channel,url=p.live_metrics_url,method=p.live_metrics_method,auth_mode=p.live_metrics_auth_mode,token=p.live_metrics_token or p.access_token,params=params)
    values:dict[str,Any]={"raw":payload}
    for metric,dotted in p.live_metric_paths.items(): values[metric]=_path(payload,dotted)
    return values


def normalized_live_metric(values:dict[str,Any],key:str,*,integer:bool=False)->int|float|None:
    n=_number(values.get(key)); return None if n is None else int(n) if integer else n
