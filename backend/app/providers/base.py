from abc import ABC, abstractmethod


class TikTokShopProvider(ABC):
    @abstractmethod
    def get_orders(self, channel_external_id: str | None, since_iso: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_products(self, channel_external_id: str | None) -> list[dict]: ...

    @abstractmethod
    def get_refunds(self, channel_external_id: str | None, since_iso: str | None = None) -> list[dict]: ...


class TikTokAdsProvider(ABC):
    @abstractmethod
    def get_metrics(self, advertiser_id: str | None, since_iso: str | None = None) -> dict: ...


class TikTokLiveProvider(ABC):
    @abstractmethod
    def get_live_status(self, channel_external_id: str | None) -> str: ...
