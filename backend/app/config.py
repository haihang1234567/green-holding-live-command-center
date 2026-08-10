from __future__ import annotations

import json
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")
    app_name:str="GREEN HOLDING LIVE COMMAND CENTER"; environment:str="development"; api_prefix:str="/api"; secret_key:str="change-this-in-production"; access_token_minutes:int=720; cors_origins:str="http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"; database_url:str="sqlite:///./green_holding.db"
    data_provider:str="MOCK"; live_status_provider:str="MOCK"; polling_interval_seconds:int=180; metric_snapshot_interval_seconds:int=180; refund_snapshot_offsets:str="0,1,3,6,12,24,48"; final_snapshot_after_hours:int=168
    admin_username:str="admin"; admin_password:str="admin123"; seed_mock_data:bool=True
    tiktok_shop_base_url:str="https://open-api.tiktokglobalshop.com"; tiktok_shop_auth_url:str="https://auth.tiktok-shops.com/api/v2"; tiktok_shop_app_key:str=""; tiktok_shop_app_secret:str=""; tiktok_shop_access_token:str=""; tiktok_shop_refresh_token:str=""; tiktok_shop_access_tokens_json:str="{}"; tiktok_shop_refresh_tokens_json:str="{}"
    tiktok_ads_base_url:str="https://business-api.tiktok.com/open_api/v1.3"; tiktok_ads_app_id:str=""; tiktok_ads_secret:str=""; tiktok_ads_access_token:str=""; tiktok_ads_metrics:str="spend,impressions,clicks,conversion"; tiktok_ads_revenue_metric:str=""; tiktok_ads_roas_metric:str=""; tiktok_webhook_secret:str=""
    tiktok_live_status_url:str=""; tiktok_live_status_method:str="GET"; tiktok_live_status_token:str=""; tiktok_live_status_channel_param:str="channel_id"; tiktok_live_status_json_path:str="data.status"; tiktok_live_value:str="LIVE"; tiktok_offline_value:str="OFFLINE"
    shop1_channel_id:int=1; shop1_name:str="SHOP 1"; shop1_shop_base_url:str="https://open-api.tiktokglobalshop.com"; shop1_auth_url:str="https://auth.tiktok-shops.com/api/v2"; shop1_app_key:str=""; shop1_app_secret:str=""; shop1_access_token:str=""; shop1_refresh_token:str=""; shop1_shop_cipher:str=""; shop1_shop_id:str=""; shop1_ads_base_url:str="https://business-api.tiktok.com/open_api/v1.3"; shop1_ads_app_id:str=""; shop1_ads_secret:str=""; shop1_ads_access_token:str=""; shop1_advertiser_id:str=""; shop1_live_status_url:str=""; shop1_live_status_method:str="GET"; shop1_live_status_auth_mode:str="BEARER"; shop1_live_status_token:str=""; shop1_live_status_channel_param:str="channel_id"; shop1_live_status_json_path:str="data.status"; shop1_live_status_mode:str="VALUE"; shop1_live_value:str="LIVE"; shop1_offline_value:str="OFFLINE"; shop1_live_source_key:str=""; shop1_live_room_id_json_path:str="data.live_room_id"; shop1_live_metrics_url:str=""; shop1_live_metrics_method:str="GET"; shop1_live_metrics_auth_mode:str="TIKTOK_SHOP"; shop1_live_metrics_token:str=""; shop1_live_metrics_room_param:str="live_room_id"; shop1_live_metric_paths_json:str="{}"
    shop2_channel_id:int=2; shop2_name:str="SHOP 2"; shop2_shop_base_url:str="https://open-api.tiktokglobalshop.com"; shop2_auth_url:str="https://auth.tiktok-shops.com/api/v2"; shop2_app_key:str=""; shop2_app_secret:str=""; shop2_access_token:str=""; shop2_refresh_token:str=""; shop2_shop_cipher:str=""; shop2_shop_id:str=""; shop2_ads_base_url:str="https://business-api.tiktok.com/open_api/v1.3"; shop2_ads_app_id:str=""; shop2_ads_secret:str=""; shop2_ads_access_token:str=""; shop2_advertiser_id:str=""; shop2_live_status_url:str=""; shop2_live_status_method:str="GET"; shop2_live_status_auth_mode:str="BEARER"; shop2_live_status_token:str=""; shop2_live_status_channel_param:str="channel_id"; shop2_live_status_json_path:str="data.status"; shop2_live_status_mode:str="VALUE"; shop2_live_value:str="LIVE"; shop2_offline_value:str="OFFLINE"; shop2_live_source_key:str=""; shop2_live_room_id_json_path:str="data.live_room_id"; shop2_live_metrics_url:str=""; shop2_live_metrics_method:str="GET"; shop2_live_metrics_auth_mode:str="TIKTOK_SHOP"; shop2_live_metrics_token:str=""; shop2_live_metrics_room_param:str="live_room_id"; shop2_live_metric_paths_json:str="{}"

    @property
    def cors_list(self)->list[str]: return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
    @property
    def refund_offsets(self)->list[int]:
        values=[]
        for item in self.refund_snapshot_offsets.split(","):
            try: values.append(int(item.strip()))
            except ValueError: continue
        return sorted(set(values or [0,1,3,6,12,24,48]))
    @property
    def shop_access_tokens(self)->dict[str,str]:
        try:
            data=json.loads(self.tiktok_shop_access_tokens_json or "{}"); return data if isinstance(data,dict) else {}
        except json.JSONDecodeError: return {}
    @property
    def shop_refresh_tokens(self)->dict[str,str]:
        try:
            data=json.loads(self.tiktok_shop_refresh_tokens_json or "{}"); return data if isinstance(data,dict) else {}
        except json.JSONDecodeError: return {}


@lru_cache
def get_settings()->Settings: return Settings()
