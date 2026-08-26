from __future__ import annotations

import asyncio
import json
import random
import string
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .database import SessionLocal
from .models import (
    AdsSnapshot,
    Alert,
    AppSetting,
    Channel,
    LiveMetricSnapshot,
    LiveSession,
    Order,
    Product,
    RefundSnapshot,
    SessionStatus,
    Team,
)
from .providers import TikTokShopProvider, providers
from .realtime import manager

settings = get_settings()
CANCEL_STATUSES = {"CANCELLED", "CANCELED", "CANCEL", "CLOSED"}


def as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def ensure_utc(value: datetime | None) -> datetime | None:
    """Normalize datetimes read from SQLite/PostgreSQL to timezone-aware UTC.

    SQLite can deserialize timezone=True columns as naive values. Keeping this normalization
    at service boundaries makes the same code safe in local SQLite tests and PostgreSQL.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_shift(now: datetime | None = None) -> str:
    # App is operated in Vietnam. Server timestamps remain UTC; shift is business metadata.
    now = now or datetime.now(timezone.utc)
    vietnam_hour = (now.astimezone(timezone(timedelta(hours=7)))).hour
    return "CA_SANG" if vietnam_hour < 16 else "CA_TOI"


def snapshot_type(hours: int | None = None, final: bool = False) -> str:
    if final:
        return "FINAL"
    return f"T+{hours or 0}H" if hours else "T+0"


def _setting(db: Session, key: str, default: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else default


def _choose_team(db: Session, channel: Channel, shift: str) -> Team:
    key = f"channel_{channel.id}_{shift.lower()}_team_id"
    configured = _setting(db, key, "")
    if configured.isdigit():
        team = db.get(Team, int(configured))
        if team:
            return team
    team = db.scalar(select(Team).order_by(Team.id))
    if not team:
        raise RuntimeError("Chưa có team trong hệ thống")
    return team


def _session_code(team: Team, channel: Channel) -> str:
    initials = "".join(word[:1].upper() for word in team.name.split())[:3]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand = "".join(random.choices(string.digits, k=3))
    return f"{initials}-CH{channel.id}-{stamp}-{rand}"


def create_alert(
    db: Session,
    alert_type: str,
    title: str,
    message: str,
    *,
    severity: str = "INFO",
    session_id: int | None = None,
    channel_id: int | None = None,
) -> Alert:
    row = Alert(
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
        session_id=session_id,
        channel_id=channel_id,
    )
    db.add(row)
    db.flush()
    return row


def start_session(db: Session, channel: Channel, team: Team, shift: str, source: str) -> LiveSession:
    existing = db.scalar(
        select(LiveSession).where(LiveSession.channel_id == channel.id, LiveSession.status == SessionStatus.LIVE.value)
    )
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    session = LiveSession(
        session_code=_session_code(team, channel),
        channel_id=channel.id,
        team_id=team.id,
        shift=shift,
        started_at=now,
        status=SessionStatus.LIVE.value,
        source=source,
    )
    channel.status = SessionStatus.LIVE.value
    db.add(session)
    db.flush()
    create_alert(
        db,
        "LIVE_STARTED",
        "LIVE STARTED",
        f"{channel.name} • {team.name} • {'Ca sáng' if shift == 'CA_SANG' else 'Ca tối'}",
        severity="LIVE",
        session_id=session.id,
        channel_id=channel.id,
    )
    return session


def stop_session(db: Session, session: LiveSession) -> LiveSession:
    if session.status == SessionStatus.ENDED.value:
        return session
    now = datetime.now(timezone.utc)
    session.status = SessionStatus.ENDED.value
    session.ended_at = now
    session.channel.status = SessionStatus.OFFLINE.value
    db.flush()
    create_refund_snapshot(db, session, 0)
    create_alert(
        db,
        "LIVE_ENDED",
        "LIVE ENDED",
        f"{session.channel.name} • {session.team.name}",
        session_id=session.id,
        channel_id=session.channel_id,
    )
    return session


def session_totals(db: Session, session_id: int) -> dict[str, Any]:
    rows = db.scalars(select(Order).where(Order.live_session_id == session_id)).all()
    original_gmv = sum(as_float(x.payment_amount) for x in rows)
    refund_amount = sum(as_float(x.refund_amount) for x in rows)
    cancelled_amount = sum(as_float(x.cancelled_amount) for x in rows)
    parent_ids = {x.parent_order_id or x.order_id for x in rows}
    cancelled_ids = {
        x.parent_order_id or x.order_id
        for x in rows
        if x.order_status.upper() in CANCEL_STATUSES or as_float(x.cancelled_amount) > 0
    }
    quantity = sum(int(x.quantity or 0) for x in rows)
    latest_ads = db.scalar(
        select(AdsSnapshot).where(AdsSnapshot.live_session_id == session_id).order_by(AdsSnapshot.timestamp.desc()).limit(1)
    )
    ads_spend = as_float(latest_ads.spend) if latest_ads else 0.0
    ads_revenue = as_float(latest_ads.gross_revenue) if latest_ads else 0.0
    net = max(0.0, original_gmv - refund_amount - cancelled_amount)
    order_count = len(parent_ids)
    return {
        "gmv": original_gmv,
        "orders": order_count,
        "quantity": quantity,
        "refund_amount": refund_amount,
        "cancelled_amount": cancelled_amount,
        "refund_rate": ((refund_amount + cancelled_amount) / original_gmv * 100) if original_gmv else 0,
        "net_revenue": net,
        "cancelled_orders": len(cancelled_ids),
        "ads_spend": ads_spend,
        "ads_revenue": ads_revenue,
        "aov": original_gmv / order_count if order_count else 0,
        "ads_percentage": ads_spend / original_gmv * 100 if original_gmv else 0,
        "roas": ads_revenue / ads_spend if ads_spend and ads_revenue else (as_float(latest_ads.roas) if latest_ads else 0),
    }


def create_metric_snapshot(db: Session, session: LiveSession) -> LiveMetricSnapshot:
    totals = session_totals(db, session.id)
    row = LiveMetricSnapshot(
        session_id=session.id,
        timestamp=datetime.now(timezone.utc),
        gmv=totals["gmv"],
        orders=totals["orders"],
        ads_spend=totals["ads_spend"],
        buyers=None,
        product_quantity=totals["quantity"],
        current_viewers=None,
        peak_viewers=None,
    )
    db.add(row)
    db.flush()
    evaluate_velocity_and_ads_alerts(db, session)
    return row


def create_refund_snapshot(db: Session, session: LiveSession, hours_after: int, final: bool = False) -> RefundSnapshot:
    stype = snapshot_type(hours_after, final)
    existing = db.scalar(
        select(RefundSnapshot).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == stype)
    )
    if existing:
        return existing
    totals = session_totals(db, session.id)
    row = RefundSnapshot(
        session_id=session.id,
        snapshot_time=datetime.now(timezone.utc),
        hours_after_live=hours_after,
        snapshot_type=stype,
        original_gmv=totals["gmv"],
        refund_amount=totals["refund_amount"],
        cancelled_amount=totals["cancelled_amount"],
        refund_cancel_rate=totals["refund_rate"],
        net_revenue=totals["net_revenue"],
        total_orders=totals["orders"],
        cancelled_orders=totals["cancelled_orders"],
    )
    db.add(row)
    db.flush()
    threshold = float(_setting(db, "refund_warning_percent", "20"))
    if row.refund_cancel_rate > threshold:
        create_alert(
            db,
            "REFUND_WARNING",
            "REFUND WARNING",
            f"{session.team.name}: hoàn/hủy {row.refund_cancel_rate:.1f}% tại {stype} vượt ngưỡng {threshold:.1f}%",
            severity="WARNING",
            session_id=session.id,
            channel_id=session.channel_id,
        )
    return row


def evaluate_velocity_and_ads_alerts(db: Session, session: LiveSession) -> None:
    now = datetime.now(timezone.utc)
    snapshots = db.scalars(
        select(LiveMetricSnapshot)
        .where(LiveMetricSnapshot.session_id == session.id, LiveMetricSnapshot.timestamp >= now - timedelta(minutes=35))
        .order_by(LiveMetricSnapshot.timestamp)
    ).all()
    if len(snapshots) >= 3:
        last = snapshots[-1]
        mid_candidates = [x for x in snapshots if (ensure_utc(x.timestamp) or now) <= now - timedelta(minutes=15)]
        old_candidates = [x for x in snapshots if (ensure_utc(x.timestamp) or now) <= now - timedelta(minutes=30)]
        if mid_candidates and old_candidates:
            mid = mid_candidates[-1]
            old = old_candidates[-1]
            recent_delta = as_float(last.gmv) - as_float(mid.gmv)
            previous_delta = as_float(mid.gmv) - as_float(old.gmv)
            drop_threshold = float(_setting(db, "gmv_velocity_drop_percent", "30"))
            if previous_delta > 0 and recent_delta < previous_delta * (1 - drop_threshold / 100):
                recent_alert = db.scalar(
                    select(Alert).where(
                        Alert.session_id == session.id,
                        Alert.alert_type == "GMV_VELOCITY_WARNING",
                        Alert.created_at >= now - timedelta(minutes=15),
                    )
                )
                if not recent_alert:
                    drop = (1 - recent_delta / previous_delta) * 100
                    create_alert(
                        db,
                        "GMV_VELOCITY_WARNING",
                        "GMV VELOCITY WARNING",
                        f"15 phút gần nhất thấp hơn khoảng {drop:.0f}% so với 15 phút trước",
                        severity="WARNING",
                        session_id=session.id,
                        channel_id=session.channel_id,
                    )
    totals = session_totals(db, session.id)
    ads_threshold = float(_setting(db, "ads_gmv_warning_percent", "8"))
    if totals["ads_percentage"] > ads_threshold:
        recent_alert = db.scalar(
            select(Alert).where(
                Alert.session_id == session.id,
                Alert.alert_type == "ADS_WARNING",
                Alert.created_at >= now - timedelta(minutes=30),
            )
        )
        if not recent_alert:
            create_alert(
                db,
                "ADS_WARNING",
                "ADS WARNING",
                f"Ads/GMV hiện {totals['ads_percentage']:.1f}% vượt ngưỡng {ads_threshold:.1f}%",
                severity="WARNING",
                session_id=session.id,
                channel_id=session.channel_id,
            )


def sync_normalized_order(db: Session, session: LiveSession, channel: Channel, row: dict[str, Any], raw: dict[str, Any]) -> None:
    if not row.get("order_id"):
        return
    # SessionLocal intentionally disables autoflush. Cache objects created during
    # this transaction so duplicate order/SKU rows in one TikTok page cannot be
    # queued as duplicate INSERTs before commit.
    order_key = str(row["order_id"])
    order_cache: dict[str, Order] = db.info.setdefault("sync_order_cache", {})
    existing = order_cache.get(order_key)
    if existing is None:
        existing = db.scalar(select(Order).where(Order.order_id == order_key))
    payload = {
        "parent_order_id": row.get("parent_order_id") or row["order_id"],
        "live_session_id": session.id,
        "channel_id": channel.id,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "sku_id": row.get("sku_id", ""),
        "product_id": row.get("product_id", ""),
        "product_name": row.get("product_name", ""),
        "quantity": row.get("quantity", 1),
        "amount": row.get("amount", 0),
        "payment_amount": row.get("payment_amount", 0),
        "currency": row.get("currency") or "VND",
        "order_status": row.get("order_status") or "UNKNOWN",
        "raw_json": json.dumps(raw, ensure_ascii=False, default=str),
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        target = existing
    else:
        target = Order(order_id=order_key, **payload)
        db.add(target)
    order_cache[order_key] = target
    if target.order_status.upper() in CANCEL_STATUSES and as_float(target.cancelled_amount) == 0:
        target.cancelled_amount = target.payment_amount
    if row.get("sku_id"):
        product_key = (str(row["sku_id"]), channel.id)
        product_cache: dict[tuple[str, int], Product] = db.info.setdefault("sync_product_cache", {})
        product = product_cache.get(product_key)
        if product is None:
            product = db.scalar(select(Product).where(Product.sku_id == product_key[0], Product.channel_id == channel.id))
        if not product:
            product = Product(
                product_id=row.get("product_id", ""),
                sku_id=product_key[0],
                product_name=row.get("product_name", ""),
                price=(as_float(row.get("amount")) / max(1, int(row.get("quantity", 1)))),
                currency=row.get("currency") or "VND",
                channel_id=channel.id,
            )
            db.add(product)
        else:
            product.product_id = row.get("product_id") or product.product_id
            product.product_name = row.get("product_name") or product.product_name
            product.price = as_float(row.get("amount")) / max(1, int(row.get("quantity", 1)))
            product.currency = row.get("currency") or product.currency
        product_cache[product_key] = product


def apply_returns(db: Session, channel: Channel, returns: list[dict[str, Any]]) -> None:
    if not isinstance(providers.shop, TikTokShopProvider):
        return
    for raw in returns:
        normalized = providers.shop.normalize_return(raw)
        parent_id = normalized["order_id"]
        if not parent_id:
            continue
        matching = db.scalars(
            select(Order).where(Order.channel_id == channel.id, or_(Order.parent_order_id == parent_id, Order.order_id == parent_id))
            .order_by(Order.id)
        ).all()
        if not matching:
            continue
        amount = normalized["refund_amount"]
        # Store the order-level refund once, on the first SKU row, to avoid double counting.
        matching[0].refund_amount = max(as_float(matching[0].refund_amount), amount)
        matching[0].updated_at = normalized["updated_at"]


async def sync_session_external(session_id: int) -> dict[str, Any]:
    if settings.data_provider.upper() != "TIKTOK":
        return {"orders": 0, "returns": 0, "ads": False, "mode": "MOCK"}
    with SessionLocal() as db:
        session = db.scalar(
            select(LiveSession).options(joinedload(LiveSession.channel), joinedload(LiveSession.team)).where(LiveSession.id == session_id)
        )
        if not session:
            return {"error": "session_not_found"}
        end = datetime.now(timezone.utc)
        session_started = ensure_utc(session.started_at) or end
        session_ended = ensure_utc(session.ended_at)
        start = max(session_started, end - timedelta(hours=3))
        # Pull updates with overlap to protect against delayed TikTok order updates.
        order_raw = await providers.shop.get_orders(session.channel, start - timedelta(minutes=5), end)
        normalized_count = 0
        if isinstance(providers.shop, TikTokShopProvider):
            for raw in order_raw:
                for row in providers.shop.normalize_order(raw):
                    # Only attribute orders whose creation time falls within this live session (+10min tolerance).
                    created = row["created_at"]
                    created = ensure_utc(created) or end
                    if created < session_started - timedelta(minutes=2):
                        continue
                    if session_ended and created > session_ended + timedelta(minutes=10):
                        continue
                    sync_normalized_order(db, session, session.channel, row, raw)
                    normalized_count += 1
        returns_raw = await providers.shop.get_returns(session.channel, start - timedelta(days=2), end)
        apply_returns(db, session.channel, returns_raw)
        ads_ok = False
        try:
            ads = await providers.ads.get_metrics(session.channel, session_started, end)
            if ads:
                db.add(AdsSnapshot(
                    live_session_id=session.id,
                    timestamp=end,
                    spend=ads.get("spend", 0),
                    impressions=ads.get("impressions", 0),
                    clicks=ads.get("clicks", 0),
                    orders=ads.get("orders", 0),
                    gross_revenue=ads.get("gross_revenue", 0),
                    roas=ads.get("roas", 0),
                ))
                ads_ok = True
        except Exception as exc:
            create_alert(db, "INTEGRATION_WARNING", "ADS SYNC WARNING", str(exc), severity="WARNING", session_id=session.id, channel_id=session.channel_id)
        create_metric_snapshot(db, session)
        db.commit()
        result = {"orders": normalized_count, "returns": len(returns_raw), "ads": ads_ok, "mode": "TIKTOK"}
    await manager.broadcast("session.updated", {"session_id": session_id, **result})
    return result


async def poll_live_statuses() -> None:
    if settings.live_status_provider.upper() == "MANUAL":
        return
    changed: list[dict[str, Any]] = []
    with SessionLocal() as db:
        channels = db.scalars(select(Channel).where(Channel.id.in_(settings.active_channel_ids),Channel.polling_enabled.is_(True)).order_by(Channel.id)).all()
        for channel in channels:
            try:
                external_status = await providers.live.get_channel_status(channel)
            except Exception as exc:
                create_alert(db, "LIVE_STATUS_ERROR", "LIVE STATUS ERROR", f"{channel.name}: {exc}", severity="WARNING", channel_id=channel.id)
                continue
            if external_status is None:
                continue
            active = db.scalar(
                select(LiveSession).options(joinedload(LiveSession.team), joinedload(LiveSession.channel)).where(
                    LiveSession.channel_id == channel.id, LiveSession.status == SessionStatus.LIVE.value
                )
            )
            if external_status == "LIVE" and not active:
                shift = local_shift()
                team = _choose_team(db, channel, shift)
                active = start_session(db, channel, team, shift, settings.live_status_provider.upper())
                changed.append({"channel_id": channel.id, "status": "LIVE", "session_id": active.id})
            elif external_status == "OFFLINE" and active:
                stop_session(db, active)
                changed.append({"channel_id": channel.id, "status": "OFFLINE", "session_id": active.id})
        db.commit()
    for event in changed:
        await manager.broadcast("channel.status", event)


async def sync_live_sessions() -> None:
    with SessionLocal() as db:
        ids = db.scalars(select(LiveSession.id).where(LiveSession.status == SessionStatus.LIVE.value,LiveSession.channel_id.in_(settings.active_channel_ids))).all()
    if settings.data_provider.upper() == "TIKTOK":
        for session_id in ids:
            try:
                await sync_session_external(session_id)
            except Exception as exc:
                with SessionLocal() as db:
                    session = db.get(LiveSession, session_id)
                    if session:
                        create_alert(db, "SHOP_SYNC_ERROR", "SHOP SYNC ERROR", str(exc), severity="WARNING", session_id=session.id, channel_id=session.channel_id)
                        db.commit()
    else:
        with SessionLocal() as db:
            sessions = db.scalars(select(LiveSession).where(LiveSession.status == SessionStatus.LIVE.value)).all()
            for session in sessions:
                create_metric_snapshot(db, session)
            db.commit()
        if ids:
            await manager.broadcast("metrics.updated", {"sessions": ids})


async def process_due_refund_snapshots() -> None:
    now = datetime.now(timezone.utc)
    due_session_ids: set[int] = set()
    with SessionLocal() as db:
        sessions = db.scalars(select(LiveSession).where(LiveSession.status == SessionStatus.ENDED.value, LiveSession.ended_at.is_not(None))).all()
        for session in sessions:
            assert session.ended_at
            ended_at = ensure_utc(session.ended_at) or now
            hours_elapsed = (now - ended_at).total_seconds() / 3600
            for hours in settings.refund_offsets:
                if hours_elapsed >= hours:
                    stype = snapshot_type(hours)
                    exists = db.scalar(select(RefundSnapshot.id).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == stype))
                    if not exists:
                        due_session_ids.add(session.id)
            if hours_elapsed >= settings.final_snapshot_after_hours:
                exists = db.scalar(select(RefundSnapshot.id).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == "FINAL"))
                if not exists:
                    due_session_ids.add(session.id)

    # Before freezing a new snapshot, pull the newest order/return state. This is what makes
    # T+3/T+24/T+48 materially different instead of repeatedly copying T+0.
    if settings.data_provider.upper() == "TIKTOK":
        for session_id in sorted(due_session_ids):
            try:
                await sync_session_external(session_id)
            except Exception as exc:
                with SessionLocal() as db:
                    session = db.get(LiveSession, session_id)
                    if session:
                        create_alert(db, "REFUND_SYNC_ERROR", "REFUND SYNC ERROR", str(exc), severity="WARNING", session_id=session.id, channel_id=session.channel_id)
                        db.commit()

    created: list[int] = []
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        sessions = db.scalars(select(LiveSession).where(LiveSession.id.in_(due_session_ids))).all() if due_session_ids else []
        for session in sessions:
            if not session.ended_at:
                continue
            ended_at = ensure_utc(session.ended_at) or now
            hours_elapsed = (now - ended_at).total_seconds() / 3600
            for hours in settings.refund_offsets:
                if hours_elapsed >= hours:
                    stype = snapshot_type(hours)
                    if not db.scalar(select(RefundSnapshot.id).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == stype)):
                        create_refund_snapshot(db, session, hours)
                        created.append(session.id)
            if hours_elapsed >= settings.final_snapshot_after_hours:
                if not db.scalar(select(RefundSnapshot.id).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == "FINAL")):
                    create_refund_snapshot(db, session, settings.final_snapshot_after_hours, final=True)
                    created.append(session.id)
        db.commit()
    if created:
        await manager.broadcast("refund.updated", {"sessions": sorted(set(created))})


def add_mock_orders(db: Session, session: LiveSession, count: int = 1, gmv_increment: float | None = None) -> None:
    products = [
        ("SERUM-A01", "Serum A01", 79500),
        ("KEM-B12", "Kem B12", 89000),
        ("COMBO-C08", "Combo C08", 149000),
        ("SRM-D05", "Sữa rửa mặt D05", 69000),
        ("MASK-E03", "Mask E03", 45000),
    ]
    now = datetime.now(timezone.utc)
    target_total = gmv_increment if gmv_increment is not None else None
    for index in range(max(1, count)):
        sku, name, price = random.choice(products)
        qty = random.choices([1, 2, 3], weights=[75, 20, 5])[0]
        amount = float(target_total / count) if target_total is not None else float(price * qty)
        oid = f"MOCK-{int(now.timestamp()*1000)}-{index}-{random.randint(1000,9999)}"
        db.add(Order(
            order_id=oid,
            parent_order_id=oid,
            live_session_id=session.id,
            channel_id=session.channel_id,
            created_at=now,
            updated_at=now,
            sku_id=sku,
            product_id=f"P-{sku}",
            product_name=name,
            quantity=qty,
            amount=amount,
            payment_amount=amount,
            currency="VND",
            order_status="AWAITING_SHIPMENT",
        ))


def add_mock_ads(db: Session, session: LiveSession, spend_increment: float) -> AdsSnapshot:
    last = db.scalar(select(AdsSnapshot).where(AdsSnapshot.live_session_id == session.id).order_by(AdsSnapshot.timestamp.desc()).limit(1))
    current = as_float(last.spend) if last else 0
    totals = session_totals(db, session.id)
    spend = current + spend_increment
    row = AdsSnapshot(
        live_session_id=session.id,
        timestamp=datetime.now(timezone.utc),
        spend=spend,
        impressions=(last.impressions if last else 0) + random.randint(500, 2500),
        clicks=(last.clicks if last else 0) + random.randint(20, 120),
        orders=totals["orders"],
        gross_revenue=totals["gmv"],
        roas=(totals["gmv"] / spend) if spend else 0,
    )
    db.add(row)
    return row


def apply_mock_refund_or_cancel(db: Session, session: LiveSession, kind: str) -> Order | None:
    candidates = db.scalars(
        select(Order).where(Order.live_session_id == session.id, Order.refund_amount == 0, Order.cancelled_amount == 0).order_by(func.random()).limit(20)
    ).all()
    if not candidates:
        return None
    row = random.choice(candidates)
    if kind == "refund":
        row.refund_amount = row.payment_amount
        row.order_status = "REFUNDED"
    else:
        row.cancelled_amount = row.payment_amount
        row.order_status = "CANCELLED"
        row.cancellation_reason = "Mock cancellation"
    row.updated_at = datetime.now(timezone.utc)
    return row


def serialize_session(db: Session, session: LiveSession) -> dict[str, Any]:
    totals = session_totals(db, session.id)
    started_at = ensure_utc(session.started_at) or datetime.now(timezone.utc)
    duration_end = ensure_utc(session.ended_at) or datetime.now(timezone.utc)
    duration = max(0, int((duration_end - started_at).total_seconds()))
    hours = max(duration / 3600, 1 / 60)
    return {
        "id": session.id,
        "session_code": session.session_code,
        "channel_id": session.channel_id,
        "channel_name": session.channel.name,
        "channel_handle": session.channel.handle,
        "team_id": session.team_id,
        "team_name": session.team.name,
        "shift": session.shift,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": session.status,
        "source": session.source,
        "duration_seconds": duration,
        **totals,
        "gmv_per_hour": totals["gmv"] / hours,
        "orders_per_hour": totals["orders"] / hours,
    }


def dashboard_overview(db: Session, team_id: int | None = None) -> dict[str, Any]:
    vn_tz = timezone(timedelta(hours=7))
    now_vn = datetime.now(vn_tz)
    day_start_vn = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = day_start_vn.astimezone(timezone.utc)
    sessions_updated_today = select(LiveMetricSnapshot.session_id).where(LiveMetricSnapshot.timestamp >= day_start)
    session_query = (
        select(LiveSession)
        .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
        .where(
            or_(LiveSession.started_at >= day_start, LiveSession.id.in_(sessions_updated_today)),
            LiveSession.channel_id.in_(settings.active_channel_ids),
        )
    )
    if team_id:
        session_query = session_query.where(LiveSession.team_id == team_id)
    sessions = db.scalars(session_query.order_by(LiveSession.started_at.desc())).unique().all()
    serialized = [serialize_session(db, s) for s in sessions]
    gmv = sum(x["gmv"] for x in serialized)
    orders = sum(x["orders"] for x in serialized)
    ads = sum(x["ads_spend"] for x in serialized)
    refunds = sum(x["refund_amount"] for x in serialized)
    cancelled = sum(x["cancelled_amount"] for x in serialized)
    net = max(0, gmv - refunds - cancelled)
    duration_hours = sum(max(x["duration_seconds"] / 3600, 0) for x in serialized)

    team_rollup: dict[int, dict[str, Any]] = {}
    for item in serialized:
        row = team_rollup.setdefault(item["team_id"], {"team_id": item["team_id"], "team_name": item["team_name"], "gmv": 0, "orders": 0, "ads": 0, "net": 0, "duration": 0})
        row["gmv"] += item["gmv"]
        row["orders"] += item["orders"]
        row["ads"] += item["ads_spend"]
        row["net"] += item["net_revenue"]
        row["duration"] += item["duration_seconds"]
    ranking = []
    for row in team_rollup.values():
        row["aov"] = row["gmv"] / row["orders"] if row["orders"] else 0
        row["ads_percentage"] = row["ads"] / row["gmv"] * 100 if row["gmv"] else 0
        row["gmv_per_hour"] = row["gmv"] / max(row["duration"] / 3600, 1 / 60)
        row["refund_rate"] = (row["gmv"] - row["net"]) / row["gmv"] * 100 if row["gmv"] else 0
        ranking.append(row)
    ranking.sort(key=lambda x: x["gmv"], reverse=True)

    order_query = select(Order.product_name, func.sum(Order.payment_amount).label("revenue"), func.sum(Order.quantity).label("quantity")).where(Order.created_at >= day_start,Order.channel_id.in_(settings.active_channel_ids))
    if team_id:
        order_query = order_query.join(LiveSession, Order.live_session_id == LiveSession.id).where(LiveSession.team_id == team_id)
    top_skus = db.execute(order_query.group_by(Order.product_name).order_by(func.sum(Order.payment_amount).desc()).limit(8)).all()

    metric_query = (
        select(LiveMetricSnapshot)
        .join(LiveSession, LiveMetricSnapshot.session_id == LiveSession.id)
        .where(LiveMetricSnapshot.timestamp >= day_start,LiveSession.channel_id.in_(settings.active_channel_ids))
    )
    if team_id:
        metric_query = metric_query.where(LiveSession.team_id == team_id)
    metric_rows = db.scalars(metric_query.order_by(LiveMetricSnapshot.timestamp)).all()
    timeline = [{"timestamp": x.timestamp, "gmv": as_float(x.gmv), "orders": x.orders, "ads_spend": as_float(x.ads_spend), "session_id": x.session_id} for x in metric_rows[-240:]]

    alert_query = select(Alert).where(Alert.created_at >= day_start,or_(Alert.channel_id.in_(settings.active_channel_ids),Alert.channel_id.is_(None))).order_by(Alert.created_at.desc()).limit(20)
    if team_id:
        alert_query = alert_query.join(LiveSession, Alert.session_id == LiveSession.id, isouter=True).where(or_(LiveSession.team_id == team_id, Alert.session_id.is_(None)))
    alerts = db.scalars(alert_query).all()

    channels = db.scalars(select(Channel).where(Channel.id.in_(settings.active_channel_ids)).order_by(Channel.id)).all()
    live_by_channel = {x.channel_id: x for x in sessions if x.status == SessionStatus.LIVE.value}
    latest_by_channel: dict[int, LiveSession] = {}
    for item in sessions:
        latest_by_channel.setdefault(item.channel_id, item)
    channel_cards = []
    for channel in channels:
        active = live_by_channel.get(channel.id)
        shown = active or latest_by_channel.get(channel.id)
        channel_cards.append({
            "id": channel.id,
            "name": channel.name,
            "handle": channel.handle,
            "status": "LIVE" if active else "OFFLINE",
            "session": serialize_session(db, shown) if shown else None,
            "is_report": bool(shown and not active),
            "shop_configured": bool(channel.shop_cipher),
            "ads_configured": bool(channel.advertiser_id),
        })

    return {
        "mode": settings.data_provider.upper(),
        "active_shop_count": len(settings.active_channel_ids),
        "live_status_mode": settings.live_status_provider.upper(),
        "kpis": {
            "gmv": gmv,
            "orders": orders,
            "ads_spend": ads,
            "aov": gmv / orders if orders else 0,
            "ads_percentage": ads / gmv * 100 if gmv else 0,
            "roas": gmv / ads if ads else 0,
            "net_revenue": net,
            "refund_rate": (refunds + cancelled) / gmv * 100 if gmv else 0,
            "gmv_per_hour": gmv / duration_hours if duration_hours else 0,
        },
        "channels": channel_cards,
        "sessions": serialized[:20],
        "ranking": ranking,
        "top_skus": [{"name": r[0] or "Chưa có tên", "revenue": as_float(r[1]), "quantity": int(r[2] or 0)} for r in top_skus],
        "timeline": timeline,
        "alerts": [{"id": a.id, "type": a.alert_type, "severity": a.severity, "title": a.title, "message": a.message, "created_at": a.created_at, "acknowledged": a.acknowledged} for a in alerts],
        "optional_metrics": {"current_viewers": None, "peak_viewers": None, "watch_time": None, "comments": None, "likes": None},
    }
