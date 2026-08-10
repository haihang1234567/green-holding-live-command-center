from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .attribution_models import OrderAttribution
from .live_models import LiveCoreSnapshot
from .models import LiveSession, Order


def _money(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("amount") or value.get("value") or 0
    try:
        text = str(value or "0").replace(",", "")
        clean = "".join(ch for ch in text if ch.isdigit() or ch in ".-")
        return float(clean or 0)
    except Exception:
        return 0.0


def _bucket(content_type: str, content_id: str, live_room_id: str | None) -> tuple[str, str, int | None]:
    ctype = (content_type or "UNKNOWN").upper()
    cid = str(content_id or "")
    room = str(live_room_id or "")
    if ctype == "LIVE":
        if room and cid and cid == room:
            return "LIVE_CURRENT", "EXACT", 1
        if cid:
            return "LIVE_OTHER", "EXACT", None
        return "LIVE_UNMATCHED", "PARTIAL", None
    if ctype in {"VIDEO", "SHOP", "PRE_LIVE", "PROMOTION_PAGE", "LINKSHARE"}:
        return ctype, "EXACT", None
    return "UNKNOWN", "UNRESOLVED", None


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
            source_bucket, confidence, attach_flag = _bucket(content_type, content_id, live_room_id)
            qty = max(1, int(sku.get("quantity") or 1))
            amount = _money(sku.get("price")) * qty
            key = "|".join([str(channel_id), order_id, sku_id, content_type, content_id])
            row = db.scalar(select(OrderAttribution).where(OrderAttribution.attribution_key == key))
            values = {
                "channel_id": channel_id,
                "session_id": session_id if attach_flag else None,
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
                for k, v in values.items():
                    setattr(row, k, v)
            else:
                row = OrderAttribution(attribution_key=key, **values)
                db.add(row)
            counts[source_bucket] += 1

            # Only an exact match to this LIVE content is permitted to join the session.
            order_rows = _find_order_rows(db, channel_id, order_id, sku_id)
            for order_row in order_rows:
                if source_bucket == "LIVE_CURRENT":
                    order_row.live_session_id = session_id
                elif order_row.live_session_id == session_id:
                    order_row.live_session_id = None
    db.flush()
    return dict(counts)


def detach_unconfirmed_session_orders(db: Session, session_id: int, order_ids: list[str]) -> None:
    """General Shop Order API is not a LIVE attribution API.

    New/updated orders are stored, but they stay detached from a LIVE session until
    TikTok content attribution explicitly confirms LIVE_CURRENT.
    """
    if not order_ids:
        return
    rows = db.scalars(select(Order).where(Order.live_session_id == session_id)).all()
    for row in rows:
        parent = str(row.parent_order_id or row.order_id).split(":", 1)[0]
        if parent not in order_ids:
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


def session_attribution_summary(db: Session, session_id: int) -> dict[str, Any]:
    session = db.get(LiveSession, session_id)
    if not session:
        return {"session_id": session_id, "sources": [], "live_analytics": None}
    attrs = db.scalars(select(OrderAttribution).where(OrderAttribution.channel_id == session.channel_id)).all()
    grouped: dict[str, dict[str, Any]] = {}
    for row in attrs:
        # LIVE_CURRENT is session-specific. Other sources are shown only if captured while this session was active.
        if row.source_bucket == "LIVE_CURRENT" and row.session_id != session_id:
            continue
        captured = row.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        start = session.started_at if session.started_at.tzinfo else session.started_at.replace(tzinfo=timezone.utc)
        end0 = session.ended_at or datetime.now(timezone.utc)
        end = end0 if end0.tzinfo else end0.replace(tzinfo=timezone.utc)
        if row.source_bucket != "LIVE_CURRENT" and not (start <= captured <= end):
            continue
        item = grouped.setdefault(row.source_bucket, {"source": row.source_bucket, "orders": set(), "sku_rows": 0, "gmv": 0.0})
        item["orders"].add(row.order_id)
        item["sku_rows"] += 1
        item["gmv"] += float(row.attributed_amount or 0)
    sources = [
        {"source": k, "orders": len(v["orders"]), "sku_rows": v["sku_rows"], "gmv": round(v["gmv"], 2)}
        for k, v in grouped.items()
    ]
    sources.sort(key=lambda x: (x["source"] != "LIVE_CURRENT", -x["gmv"]))
    live = db.scalar(select(LiveCoreSnapshot).where(LiveCoreSnapshot.session_id == session_id).order_by(LiveCoreSnapshot.captured_at.desc()).limit(1))
    return {
        "session_id": session_id,
        "rule": "Only TikTok-confirmed LIVE_CURRENT attribution is counted as an exact LIVE order. UNKNOWN is never promoted by time-window inference.",
        "sources": sources,
        "live_analytics": None if not live else {
            "gmv": float(live.gmv or 0),
            "orders": int(live.orders or 0),
            "paid_orders": int(live.paid_orders or 0),
            "buyers": int(live.buyers or 0),
            "captured_at": live.captured_at,
        },
    }
