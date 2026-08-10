from __future__ import annotations

import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "GREEN HOLDING LIVE COMMAND CENTER"
    environment: str = "development"
    api_prefix: str = "/api"
    secret_key: str = "change-this-in-production"
    access_token_minutes: int = 720
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    database_url: str = "sqlite:///./green_holding.db"
    data_provider: str = "MOCK"  # MOCK | TIKTOK
    live_status_provider: str = "MOCK"  # MOCK | MANUAL | TIKTOK_ENDPOINT
    polling_interval_seconds: int = 180
    metric_snapshot_interval_seconds: int = 180
    refund_snapshot_offsets: str = "0,1,3,6,12,24,48"
    final_snapshot_after_hours: int = 168

    admin_username: str = "admin"
    admin_password: str = "admin123"
    seed_mock_data: bool = True

    # TikTok Shop Open API
    tiktok_shop_base_url: str = "https://open-api.tiktokglobalshop.com"
    tiktok_shop_auth_url: str = "https://auth.tiktok-shops.com/api/v2"
    tiktok_shop_app_key: str = ""
    tiktok_shop_app_secret: str = ""
    tiktok_shop_access_token: str = ""
    tiktok_shop_refresh_token: str = ""
    # Optional map: {"SHOP_CIPHER_1": "token1", "SHOP_CIPHER_2": "token2"}
    tiktok_shop_access_tokens_json: str = "{}"
    tiktok_shop_refresh_tokens_json: str = "{}"

    # TikTok API for Business / Marketing API
    tiktok_ads_base_url: str = "https://business-api.tiktok.com/open_api/v1.3"
    tiktok_ads_app_id: str = ""
    tiktok_ads_secret: str = ""
    tiktok_ads_access_token: str = ""
    tiktok_ads_metrics: str = "spend,impressions,clicks,conversion"
    tiktok_ads_revenue_metric: str = ""
    tiktok_ads_roas_metric: str = ""

    # Optional future/allowlisted LIVE status endpoint.
    tiktok_live_status_url: str = ""
    tiktok_live_status_method: str = "GET"
    tiktok_live_status_token: str = ""
    tiktok_live_status_channel_param: str = "channel_id"
    tiktok_live_status_json_path: str = "data.status"
    tiktok_live_value: str = "LIVE"
    tiktok_offline_value: str = "OFFLINE"

    # Webhook verification can be filled after TikTok provides the exact secret/signature contract.
    tiktok_webhook_secret: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def refund_offsets(self) -> list[int]:
        values: list[int] = []
        for item in self.refund_snapshot_offsets.split(","):
            try:
                values.append(int(item.strip()))
            except ValueError:
                continue
        return sorted(set(values or [0, 1, 3, 6, 12, 24, 48]))

    @property
    def shop_access_tokens(self) -> dict[str, str]:
        try:
            data = json.loads(self.tiktok_shop_access_tokens_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @property
    def shop_refresh_tokens(self) -> dict[str, str]:
        try:
            data = json.loads(self.tiktok_shop_refresh_tokens_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
