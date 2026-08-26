from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .live_runtime import get_live_metrics, shop_client
from .models import Channel


async def get_best_live_metrics(channel: Channel, live_room_id: str | None) -> dict[str, Any] | None:
    """Read seller-authorized metrics from Shop LIVE Performance.

    The session id returned by this endpoint is not a LIVE Core Stats room id,
    so it must never be passed to `/live_rooms/{id}/core_stats`.
    """
    client, _ = shop_client(channel)
    shop_now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    sessions = await client.get_shop_live_sessions(
        channel,
        (shop_now.date() - timedelta(days=1)).isoformat(),
        (shop_now.date() + timedelta(days=1)).isoformat(),
    )

    selected = None
    if live_room_id:
        selected = next(
            (
                item
                for item in sessions
                if str(item.get("id") or item.get("live_id") or item.get("live_room_id") or "")
                == str(live_room_id)
            ),
            None,
        )
    if selected is None:
        selected = next(
            (
                item
                for item in sessions
                if str(item.get("status") or item.get("live_status") or "").upper()
                in {"LIVE", "ONGOING", "IN_PROGRESS", "STREAMING"}
                or not item.get("end_time")
            ),
            sessions[0] if sessions else None,
        )

    if selected:
        sales = selected.get("sales_performance") or {}
        if not isinstance(sales, dict):
            sales = {}
        return {
            "gmv": sales.get("gmv"),
            "orders": sales.get("created_sku_orders") or sales.get("sku_orders") or sales.get("main_orders"),
            "paid_orders": sales.get("sku_orders") or sales.get("main_orders"),
            "buyers": sales.get("customers"),
            "current_viewers": None,
            "peak_viewers": None,
            "product_views": None,
            "ctr": None,
            "comments": None,
            "shares": None,
            "avg_watch_seconds": None,
            "items_sold": sales.get("items_sold") or sales.get("units_sold"),
            "raw": selected,
            "source": "TIKTOK_SHOP_LIVE_PERFORMANCE",
        }

    # Preserve support for an explicitly configured custom metrics endpoint.
    return await get_live_metrics(channel, live_room_id)
