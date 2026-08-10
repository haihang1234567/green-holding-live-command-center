import random
from app.providers.base import TikTokShopProvider, TikTokAdsProvider, TikTokLiveProvider


class MockTikTokShopProvider(TikTokShopProvider):
    def get_orders(self, channel_external_id: str | None, since_iso: str | None = None) -> list[dict]:
        return []

    def get_products(self, channel_external_id: str | None) -> list[dict]:
        return [
            {"product_id": "P001", "sku_id": "SKU001", "product_name": "Sản phẩm A", "price": 79000},
            {"product_id": "P002", "sku_id": "SKU002", "product_name": "Sản phẩm B", "price": 129000},
            {"product_id": "P003", "sku_id": "SKU003", "product_name": "Sản phẩm C", "price": 59000},
        ]

    def get_refunds(self, channel_external_id: str | None, since_iso: str | None = None) -> list[dict]:
        return []


class MockTikTokAdsProvider(TikTokAdsProvider):
    def get_metrics(self, advertiser_id: str | None, since_iso: str | None = None) -> dict:
        return {"spend": random.randint(100_000, 600_000), "gross_revenue": random.randint(2_000_000, 8_000_000)}


class MockTikTokLiveProvider(TikTokLiveProvider):
    def get_live_status(self, channel_external_id: str | None) -> str:
        return "OFFLINE"
