from app.core.config import get_settings
from app.providers.mock import MockTikTokShopProvider, MockTikTokAdsProvider, MockTikTokLiveProvider
from app.providers.tiktok import RealTikTokShopProvider, RealTikTokAdsProvider, RealTikTokLiveProvider


def providers():
    settings = get_settings()
    if settings.data_provider.upper() == "TIKTOK":
        return RealTikTokShopProvider(), RealTikTokAdsProvider(), RealTikTokLiveProvider()
    return MockTikTokShopProvider(), MockTikTokAdsProvider(), MockTikTokLiveProvider()
