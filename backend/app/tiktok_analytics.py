from __future__ import annotations

from typing import Any

from .live_runtime import get_live_metrics, shop_client
from .models import Channel


def _get(data: Any, *path: str):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


async def get_best_live_metrics(channel: Channel, live_room_id: str | None) -> dict[str, Any] | None:
    """Prefer TikTok Shop's official LIVE Core Stats endpoint.

    Required scope depends on the approved analytics permissions. If a custom
    endpoint was configured instead, the existing generic mapper remains a fallback.
    """
    if live_room_id:
        client, _ = shop_client(channel)
        path = f"/analytics/202502/live_rooms/{live_room_id}/core_stats"
        payload = await client._request("GET", path, channel)
        stats = _get(payload, "data", "stats") or {}
        if isinstance(stats, dict) and stats:
            return {
                "gmv": stats.get("local_gmv"),
                "orders": stats.get("created_order_count"),
                "paid_orders": stats.get("paid_order_count"),
                "buyers": stats.get("buyer_count"),
                "current_viewers": stats.get("current_visitor_count"),
                "peak_viewers": stats.get("peak_concurrent_user_count"),
                "product_views": stats.get("product_view_count"),
                "ctr": stats.get("click_through_rate"),
                "comments": stats.get("accumulated_comment_count"),
                "shares": stats.get("accumulated_sharing_count"),
                "avg_watch_seconds": stats.get("avg_watching_duration"),
                "items_sold": stats.get("sales"),
                "raw": payload,
                "source": "TIKTOK_LIVE_CORE_STATS",
            }
    return await get_live_metrics(channel, live_room_id)
