from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .attribution_models import OrderAttribution
from .live_models import LiveCoreSnapshot
from .models import AdsSnapshot, LiveSession, Order, RefundSnapshot

CANCEL_STATUSES = {"CANCELLED", "CANCELED", "CANCEL", "CLOSED"}


def _money(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("amount") or value.get("value") or 0
    try:
        text = str(value or "0").replace(",", "")
        clean = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
        return float(clean or 0)
    except Exception:
        return 0.0


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _bucket(content_type: str, content_id: str, live_room_id: str | None) -> tuple[str, str, bool]:
    ctype = (content_type or "UNKNOWN").upper()
    cid = str(content_id or "")
    room = str(live_room_id or "")
    if ctype == "LIVE":
        if room and cid and cid == room:
            return "LIVE_CURRENT", "EXACT", True
        if cid:
            return "LIVE_OTHER", "EXACT", False
        return "LIVE_UNMATCHED", "PARTIAL", False
    if ctype in {"VIDEO", "SHOP", "PRE_LIVE", "PROMOTION_PAGE", "LINKSHARE"}:
        return ctype, "EXACT", False
    return "UNKNOWN", "UNRESOLVED", False


def _find_order_rows(db: Session, channel_id: int, order_id: str, sku_id: str) -> list[Order]:
    query = select(Order).where(
        Order.channel_id == channel_id,
        or_(Order.parent_order_id == order_id, Order.order_id == order_id, Order.order_id.like(f"{order_id}:%")),
    )
    rows = db.scalars(query).all()
    if sku_id:
        sku_rows = [row for row in rows if str(row.sku_id or "") == sku_id]
        return sku_rows or rows
    return rows


def upsert_affiliate_attributions(
    db: Session,
    *,
    channel_id: int,
    session_id: int,
    live_room_id: str | None,
    raw_orders: list[dict[str, Any]],
) -> dict[str, int]:
    """Persist TikTok's explicit affiliate content_type/content_id attribution."""
    counts: dict[str, int] = defaultdict(int)
    now = datetime.now(timezone.utc)
    for raw in raw_orders:
        order_id = str(raw.get("id") or raw.get("order_id") or "")
        if not order_id:
            continue
        skus = raw.get("skus") or raw.get("items") or []
        if isinstance(skus, dict):
            skus = [skus]
        for sku in skus:
            sku_id = str(sku.get("id") or sku.get("sku_id") or "")
            content_type = str(sku.get("content_type") or "UNKNOWN").upper()
            content_id = str(sku.get("content_id") or "")
            source_bucket, confidence, is_current_live = _bucket(content_type, content_id, live_room_id)
            qty = max(1, int(sku.get("quantity") or 1))
            amount = _money(sku.get("price")) * qty
            key = "|".join([str(channel_id), order_id, sku_id, content_type, content_id])
            row = db.scalar(select(OrderAttribution).where(OrderAttribution.attribution_key == key))
            values = {
                "channel_id": channel_id,
                "session_id": session_id if is_current_live else None,
                "order_id": order_id,
                "sku_id": sku_id,
                "product_id": str(sku.get("product_id") or ""),
                "creator_username": str(sku.get("creator_username") or ""),
                "content_type": content_type,
                "content_id": content_id,
                "source_bucket": source_bucket,
                "confidence": confidence,
                "is_affiliate": True,
                "quantity": qty,
                "attributed_amount": amount,
                "currency": (sku.get("price") or {}).get("currency", "VND") if isinstance(sku.get("price"), dict) else "VND",
                "raw_json": json.dumps({"order": raw, "sku": sku}, ensure_ascii=False, default=str),
                "captured_at": now,
            }
            if row:
                for key0, value in values.items():
                    setattr(row, key0, value)
            else:
                row = OrderAttribution(attribution_key=key, **values)
                db.add(row)
            counts[source_bucket] += 1

            # General Order API data is never enough to call an order a LIVE order.
            # Only TikTok content_type=LIVE + matching content_id may attach it.
            for order_row in _find_order_rows(db, channel_id, order_id, sku_id):
                if is_current_live:
                    order_row.live_session_id = session_id
                elif order_row.live_session_id == session_id:
                    order_row.live_session_id = None
    db.flush()
    return dict(counts)


def detach_unconfirmed_session_orders(db: Session, session_id: int, order_ids: list[str]) -> None:
    """Detach time-window-only orders until explicit LIVE attribution confirms them."""
    if not order_ids:
        return
    rows = db.scalars(select(Order).where(Order.live_session_id == session_id)).all()
    wanted = set(order_ids)
    for row in rows:
        parent = str(row.parent_order_id or row.order_id).split(":", 1)[0]
        if parent not in wanted:
            continue
        exact = db.scalar(
            select(OrderAttribution.id).where(
                OrderAttribution.session_id == session_id,
                OrderAttribution.order_id == parent,
                OrderAttribution.source_bucket == "LIVE_CURRENT",
            ).limit(1)
        )
        if not exact:
            row.live_session_id = None
    db.flush()


def session_live_totals(db: Session, session_id: int) -> dict[str, Any]:
    """LIVE KPI source of truth.

    GMV/order count prefer TikTok LIVE Analytics. Refund/cancel amounts use only
    order rows that have exact LIVE attribution. This prevents natural/video/link
    orders from inflating LIVE performance.
    """
    live = db.scalar(
        select(LiveCoreSnapshot)
        .where(LiveCoreSnapshot.session_id == session_id)
        .order_by(LiveCoreSnapshot.captured_at.desc())
        .limit(1)
    )
    exact_orders = db.scalars(select(Order).where(Order.live_session_id == session_id)).all()
    parent_ids = {str(x.parent_order_id or x.order_id).split(":", 1)[0] for x in exact_orders}
    exact_gmv = sum(float(x.payment_amount or 0) for x in exact_orders)
    gmv = float(live.gmv) if live and live.gmv is not None else exact_gmv
    orders = int(live.orders) if live and live.orders is not None else len(parent_ids)
    refund = sum(float(x.refund_amount or 0) for x in exact_orders)
    cancelled = sum(float(x.cancelled_amount or 0) for x in exact_orders)
    cancelled_ids = {
        str(x.parent_order_id or x.order_id).split(":", 1)[0]
        for x in exact_orders
        if (x.order_status or "").upper() in CANCEL_STATUSES or float(x.cancelled_amount or 0) > 0
    }
    latest_ads = db.scalar(
        select(AdsSnapshot).where(AdsSnapshot.live_session_id == session_id).order_by(AdsSnapshot.timestamp.desc()).limit(1)
    )
    ads_spend = float(latest_ads.spend or 0) if latest_ads else 0.0
    ads_revenue = float(latest_ads.gross_revenue or 0) if latest_ads else 0.0
    net = max(0.0, gmv - refund - cancelled)
    return {
        "gmv": gmv,
        "orders": orders,
        "paid_orders": int(live.paid_orders or 0) if live else 0,
        "buyers": int(live.buyers or 0) if live else 0,
        "quantity": sum(int(x.quantity or 0) for x in exact_orders),
        "refund_amount": refund,
        "cancelled_amount": cancelled,
        "refund_rate": ((refund + cancelled) / gmv * 100) if gmv else 0.0,
        "net_revenue": net,
        "cancelled_orders": len(cancelled_ids),
        "ads_spend": ads_spend,
        "ads_revenue": ads_revenue,
        "aov": gmv / orders if orders else 0.0,
        "ads_percentage": ads_spend / gmv * 100 if gmv else 0.0,
        "roas": ads_revenue / ads_spend if ads_spend and ads_revenue else (float(latest_ads.roas or 0) if latest_ads else 0.0),
        "metric_source": "TIKTOK_LIVE_ANALYTICS" if live and live.gmv is not None else "EXACT_ATTRIBUTED_ORDERS",
    }


def override_serialized_session(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload or not payload.get("id"):
        return payload
    totals = session_live_totals(db, int(payload["id"]))
    payload.update(totals)
    duration = max(0, int(payload.get("duration_seconds") or 0))
    hours = max(duration / 3600, 1 / 60)
    payload["gmv_per_hour"] = totals["gmv"] / hours
    payload["orders_per_hour"] = totals["orders"] / hours
    return payload


def refresh_refund_snapshot(db: Session, session: LiveSession, hours_after: int, *, final: bool = False) -> RefundSnapshot:
    stype = "FINAL" if final else ("T+0" if hours_after == 0 else f"T+{hours_after}H")
    totals = session_live_totals(db, session.id)
    row = db.scalar(select(RefundSnapshot).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == stype))
    if not row:
        row = RefundSnapshot(session_id=session.id, snapshot_type=stype, hours_after_live=hours_after)
        db.add(row)
    row.snapshot_time = datetime.now(timezone.utc)
    row.original_gmv = totals["gmv"]
    row.refund_amount = totals["refund_amount"]
    row.cancelled_amount = totals["cancelled_amount"]
    row.refund_cancel_rate = totals["refund_rate"]
    row.net_revenue = totals["net_revenue"]
    row.total_orders = totals["orders"]
    row.cancelled_orders = totals["cancelled_orders"]
    db.flush()
    return row


def session_attribution_summary(db: Session, session_id: int) -> dict[str, Any]:
    session = db.get(LiveSession, session_id)
    if not session:
        return {"session_id": session_id, "sources": [], "live_analytics": None}
    attrs = db.scalars(select(OrderAttribution).where(OrderAttribution.channel_id == session.channel_id)).all()
    grouped: dict[str, dict[str, Any]] = {}
    start = _aware(session.started_at) or datetime.now(timezone.utc)
    end = _aware(session.ended_at) or datetime.now(timezone.utc)
    for row in attrs:
        if row.source_bucket == "LIVE_CURRENT":
            if row.session_id != session_id:
                continue
        else:
            captured = _aware(row.captured_at) or datetime.now(timezone.utc)
            if not (start <= captured <= end):
                continue
        item = grouped.setdefault(row.source_bucket, {"source": row.source_bucket, "orders": set(), "sku_rows": 0, "gmv": 0.0})
        item["orders"].add(row.order_id)
        item["sku_rows"] += 1
        item["gmv"] += float(row.attributed_amount or 0)
    sources = [
        {"source": key, "orders": len(value["orders"]), "sku_rows": value["sku_rows"], "gmv": round(value["gmv"], 2)}
        for key, value in grouped.items()
    ]
    sources.sort(key=lambda x: (x["source"] != "LIVE_CURRENT", -x["gmv"]))
    totals = session_live_totals(db, session_id)
    live = db.scalar(select(LiveCoreSnapshot).where(LiveCoreSnapshot.session_id == session_id).order_by(LiveCoreSnapshot.captured_at.desc()).limit(1))
    return {
        "session_id": session_id,
        "rule": "LIVE GMV uses TikTok LIVE Analytics. Order-level LIVE attribution requires content_type=LIVE and content_id matching this live_room_id. Time alone never promotes an order to LIVE.",
        "live_totals": totals,
        "sources": sources,
        "live_analytics": None if not live else {
            "gmv": float(live.gmv or 0),
            "orders": int(live.orders or 0),
            "paid_orders": int(live.paid_orders or 0),
            "buyers": int(live.buyers or 0),
            "captured_at": live.captured_at,
        },
    }
