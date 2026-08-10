from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Live Command Center"
    environment: str = "development"
    secret_key: str = "change-me-before-production"
    access_token_expire_minutes: int = 720
    database_url: str = "sqlite:///./live_command_center.db"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    data_provider: str = "MOCK"
    poll_interval_seconds: int = 60
    mock_tick_seconds: int = 12

    # TikTok credentials: backend only
    tiktok_shop_app_key: str | None = None
    tiktok_shop_app_secret: str | None = None
    tiktok_shop_access_token: str | None = None
    tiktok_ads_app_id: str | None = None
    tiktok_ads_secret: str | None = None
    tiktok_ads_access_token: str | None = None

    # Optional API endpoint mapping. Leave blank until API package is approved.
    tiktok_shop_orders_url: str | None = None
    tiktok_shop_products_url: str | None = None
    tiktok_shop_refunds_url: str | None = None
    tiktok_ads_metrics_url: str | None = None
    tiktok_live_status_url: str | None = None

    # Field mapping (JSON dotted paths) for real adapters.
    map_order_id: str = "order_id"
    map_order_amount: str = "amount"
    map_order_status: str = "status"
    map_product_id: str = "product_id"
    map_sku_id: str = "sku_id"
    map_live_status: str = "status"

    admin_username: str = "admin"
    admin_password: str = "admin123"
    team_default_password: str = "team123"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
