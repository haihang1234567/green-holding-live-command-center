from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from .attribution import (
    detach_unconfirmed_session_orders,
    refresh_refund_snapshot,
    session_live_totals,
    upsert_affiliate_attributions,
)
from .config import get_settings
from .database import SessionLocal
from .live_models import LiveCoreSnapshot
from .live_runtime import (
    ads_client,
    get_affiliate_orders,
    get_live_signal,
    normalized_live_metric,
    profile_for_channel,
    shop_client,
)
from .models import AdsSnapshot, Alert, AppSetting, Channel, LiveMetricSnapshot, LiveSession, Order, RefundSnapshot, SessionStatus
from .providers import TikTokShopProvider
from .realtime import manager
from .services import _choose_team, create_alert, create_metric_snapshot, local_shift, snapshot_type, start_session, stop_session, sync_normalized_order
from .tiktok_analytics import get_best_live_metrics

settings = get_settings()
monitor_state: dict[str, Any] = {"last_cycle_at": None, "last_cycle_duration_ms": None, "channels": {}}


def _aware(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _active_room(db, channel_id: int):
    row = db.get(AppSetting, f"channel_{channel_id}_active_live_room_id")
    return row.value if row and row.value else None


def _set_active_room(db, channel_id: int, room_id):
    key = f"channel_{channel_id}_active_live_room_id"
    row = db.get(AppSetting, key)
    if row:
        row.value = room_id or ""
    else:
        db.add(AppSetting(key=key, value=room_id or ""))


def _recent_alert_exists(db, channel_id: int, alert_type: str, minutes: int = 30) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return bool(
        db.scalar(
            select(Alert.id)
            .where(Alert.channel_id == channel_id, Alert.alert_type == alert_type, Alert.created_at >= cutoff)
            .limit(1)
        )
    )


def _apply_returns(db, channel, rows):
    count = 0
    for raw in rows:
        normalized = TikTokShopProvider.normalize_return(raw)
        parent = normalized.get("order_id")
        if not parent:
            continue
        matching = db.scalars(
            select(Order)
            .where(Order.channel_id == channel.id, or_(Order.parent_order_id == parent, Order.order_id == parent))
            .order_by(Order.id)
        ).all()
        if not matching:
            continue
        matching[0].refund_amount = max(float(matching[0].refund_amount or 0), float(normalized.get("refund_amount") or 0))
        matching[0].updated_at = normalized.get("updated_at") or datetime.now(timezone.utc)
        count += 1
    return count


def _record_live_metric_snapshot(db, session: LiveSession) -> None:
    totals = session_live_totals(db, session.id)
    core = db.scalar(
        select(LiveCoreSnapshot)
        .where(LiveCoreSnapshot.session_id == session.id)
        .order_by(LiveCoreSnapshot.captured_at.desc())
        .limit(1)
    )
    db.add(
        LiveMetricSnapshot(
            session_id=session.id,
            timestamp=datetime.now(timezone.utc),
            gmv=totals["gmv"],
            orders=totals["orders"],
            ads_spend=totals["ads_spend"],
            buyers=(core.buyers if core else None),
            product_quantity=totals["quantity"],
            current_viewers=(core.current_viewers if core else None),
            peak_viewers=(core.peak_viewers if core else None),
        )
    )


async def sync_session(session_id: int, *, record_live_core: bool = True, record_metric: bool = True) -> dict[str, Any]:
    with SessionLocal() as db:
        session = db.scalar(
            select(LiveSession)
            .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
            .where(LiveSession.id == session_id)
        )
        if not session:
            return {"ok": False, "error": "session_not_found"}
        if settings.data_provider.upper() != "TIKTOK":
            if record_metric:
                create_metric_snapshot(db, session)
            db.commit()
            return {"ok": True, "mode": "MOCK", "orders": 0, "returns": 0, "ads": False, "live_core": False}

        channel = session.channel
        shop, _ = shop_client(channel)
        ads, _ = ads_client(channel)
        now = datetime.now(timezone.utc)
        started = _aware(session.started_at) or now
        ended = _aware(session.ended_at)
        latest_metric = db.scalar(
            select(LiveMetricSnapshot)
            .where(LiveMetricSnapshot.session_id == session.id)
            .order_by(LiveMetricSnapshot.timestamp.desc())
            .limit(1)
        )
        watermark = _aware(latest_metric.timestamp) if latest_metric else None
        orders_from = max(started, (watermark or started) - timedelta(minutes=10))

        # General Shop orders are stored, but never assumed to be LIVE from time alone.
        raw_orders = await shop.get_orders(channel, orders_from, now)
        normalized_count = 0
        touched_parent_ids: set[str] = set()
        for raw in raw_orders:
            for row in TikTokShopProvider.normalize_order(raw):
                created = _aware(row.get("created_at")) or now
                if created < started - timedelta(minutes=2) or (ended and created > ended + timedelta(minutes=10)):
                    continue
                sync_normalized_order(db, session, channel, row, raw)
                touched_parent_ids.add(str(row.get("parent_order_id") or row.get("order_id") or "").split(":", 1)[0])
                normalized_count += 1
        db.flush()
        detach_unconfirmed_session_orders(db, session.id, [x for x in touched_parent_ids if x])

        # Affiliate Orders provides explicit content_type/content_id attribution.
        attribution_counts: dict[str, int] = {}
        affiliate_ok = False
        try:
            affiliate_orders = await get_affiliate_orders(channel, started, ended or now)
            attribution_counts = upsert_affiliate_attributions(
                db,
                channel_id=channel.id,
                session_id=session.id,
                live_room_id=_active_room(db, channel.id),
                raw_orders=affiliate_orders,
            )
            affiliate_ok = True
        except Exception as exc:
            if not _recent_alert_exists(db, channel.id, "AFFILIATE_ATTRIBUTION_WARNING"):
                create_alert(
                    db,
                    "AFFILIATE_ATTRIBUTION_WARNING",
                    "AFFILIATE ATTRIBUTION WARNING",
                    f"{channel.name}: {exc}",
                    severity="WARNING",
                    session_id=session.id,
                    channel_id=channel.id,
                )

        raw_returns = await shop.get_returns(channel, max(started, now - timedelta(days=8)), now)
        return_count = _apply_returns(db, channel, raw_returns)

        ads_ok = False
        try:
            ad = await ads.get_metrics(channel, started, ended or now)
            if ad:
                db.add(
                    AdsSnapshot(
                        live_session_id=session.id,
                        timestamp=now,
                        spend=ad.get("spend", 0),
                        impressions=ad.get("impressions", 0),
                        clicks=ad.get("clicks", 0),
                        orders=ad.get("orders", 0),
                        gross_revenue=ad.get("gross_revenue", 0),
                        roas=ad.get("roas", 0),
                    )
                )
                ads_ok = True
        except Exception as exc:
            if not _recent_alert_exists(db, channel.id, "ADS_SYNC_WARNING"):
                create_alert(db, "ADS_SYNC_WARNING", "ADS SYNC WARNING", f"{channel.name}: {exc}", severity="WARNING", session_id=session.id, channel_id=channel.id)

        # Official LIVE Core Stats by live_room_id is the primary KPI source.
        live_core_ok = False
        if record_live_core:
            try:
                values = await get_best_live_metrics(channel, _active_room(db, channel.id))
                if values:
                    db.add(
                        LiveCoreSnapshot(
                            session_id=session.id,
                            channel_id=channel.id,
                            captured_at=now,
                            gmv=normalized_live_metric(values, "gmv"),
                            orders=normalized_live_metric(values, "orders", integer=True),
                            paid_orders=normalized_live_metric(values, "paid_orders", integer=True),
                            buyers=normalized_live_metric(values, "buyers", integer=True),
                            current_viewers=normalized_live_metric(values, "current_viewers", integer=True),
                            peak_viewers=normalized_live_metric(values, "peak_viewers", integer=True),
                            product_views=normalized_live_metric(values, "product_views", integer=True),
                            ctr=normalized_live_metric(values, "ctr"),
                            comments=normalized_live_metric(values, "comments", integer=True),
                            shares=normalized_live_metric(values, "shares", integer=True),
                            avg_watch_seconds=normalized_live_metric(values, "avg_watch_seconds"),
                            raw_json=json.dumps(values.get("raw") or {}, ensure_ascii=False, default=str),
                        )
                    )
                    live_core_ok = True
            except Exception as exc:
                if not _recent_alert_exists(db, channel.id, "LIVE_METRIC_WARNING"):
                    create_alert(db, "LIVE_METRIC_WARNING", "LIVE METRIC WARNING", f"{channel.name}: {exc}", severity="WARNING", session_id=session.id, channel_id=channel.id)

        db.flush()
        if record_metric:
            _record_live_metric_snapshot(db, session)
        db.commit()

    result = {
        "ok": True,
        "mode": "TIKTOK",
        "shop_orders_seen": normalized_count,
        "returns": return_count,
        "ads": ads_ok,
        "live_core": live_core_ok,
        "affiliate_attribution": affiliate_ok,
        "source_counts": attribution_counts,
    }
    await manager.broadcast("session.updated", {"session_id": session_id, **result})
    return result


async def monitor_cycle() -> None:
    began = datetime.now(timezone.utc)
    events: list[dict[str, Any]] = []
    with SessionLocal() as db:
        ids = list(db.scalars(select(Channel.id).where(Channel.polling_enabled.is_(True)).order_by(Channel.id)).all())

    for channel_id in ids:
        signal: dict[str, Any] = {"status": "UNKNOWN"}
        session_id: int | None = None
        with SessionLocal() as db:
            channel = db.get(Channel, channel_id)
            if not channel:
                continue
            profile = profile_for_channel(channel)
            state: dict[str, Any] = {"shop": profile.name, "channel_id": channel.id, "checked_at": datetime.now(timezone.utc).isoformat()}
            try:
                signal = await get_live_signal(channel)
                state.update(signal=signal["status"], live_room_id=signal.get("live_room_id"), error=None)
            except Exception as exc:
                state.update(signal="UNKNOWN", error=str(exc))
                if not _recent_alert_exists(db, channel.id, "LIVE_STATUS_ERROR"):
                    create_alert(db, "LIVE_STATUS_ERROR", "LIVE STATUS ERROR", f"{channel.name}: {exc}", severity="WARNING", channel_id=channel.id)
                db.commit()
                monitor_state["channels"][str(channel.id)] = state
                continue

            active = db.scalar(
                select(LiveSession)
                .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
                .where(LiveSession.channel_id == channel.id, LiveSession.status == SessionStatus.LIVE.value)
            )
            session_id = active.id if active else None

            if signal["status"] == "LIVE" and not active:
                shift = local_shift()
                team = _choose_team(db, channel, shift)
                active = start_session(db, channel, team, shift, "AUTO_API")
                _set_active_room(db, channel.id, signal.get("live_room_id"))
                db.commit()
                session_id = active.id
                events.append({"channel_id": channel.id, "channel_name": channel.name, "shop": profile.name, "status": "LIVE", "session_id": session_id})

            elif signal["status"] == "OFFLINE" and active:
                session_id = active.id
                db.commit()
                try:
                    await sync_session(session_id)
                except Exception as exc:
                    with SessionLocal() as adb:
                        if not _recent_alert_exists(adb, channel.id, "FINAL_SYNC_WARNING"):
                            create_alert(adb, "FINAL_SYNC_WARNING", "FINAL SYNC WARNING", f"{channel.name}: {exc}", severity="WARNING", session_id=session_id, channel_id=channel.id)
                            adb.commit()
                with SessionLocal() as cdb:
                    closing = cdb.scalar(
                        select(LiveSession)
                        .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
                        .where(LiveSession.id == session_id)
                    )
                    if closing and closing.status == SessionStatus.LIVE.value:
                        stop_session(cdb, closing)
                        refresh_refund_snapshot(cdb, closing, 0)
                        _set_active_room(cdb, channel.id, None)
                        cdb.commit()
                events.append({"channel_id": channel.id, "channel_name": channel.name, "shop": profile.name, "status": "OFFLINE", "session_id": session_id})
                state["session_id"] = session_id
                monitor_state["channels"][str(channel.id)] = state
                continue

            elif signal["status"] == "LIVE" and signal.get("live_room_id"):
                _set_active_room(db, channel.id, signal.get("live_room_id"))
                db.commit()

            state["session_id"] = session_id
            monitor_state["channels"][str(channel.id)] = state

        if session_id and signal["status"] == "LIVE":
            try:
                result = await sync_session(session_id)
                monitor_state["channels"][str(channel_id)]["source_counts"] = result.get("source_counts", {})
            except Exception as exc:
                with SessionLocal() as adb:
                    if not _recent_alert_exists(adb, channel_id, "SHOP_SYNC_ERROR"):
                        create_alert(adb, "SHOP_SYNC_ERROR", "SHOP SYNC ERROR", str(exc), severity="WARNING", session_id=session_id, channel_id=channel_id)
                        adb.commit()

    for event in events:
        await manager.broadcast("channel.status", event)
    finished = datetime.now(timezone.utc)
    monitor_state["last_cycle_at"] = finished.isoformat()
    monitor_state["last_cycle_duration_ms"] = round((finished - began).total_seconds() * 1000)


async def refund_cycle() -> None:
    now = datetime.now(timezone.utc)
    due: dict[int, list[tuple[int, bool]]] = {}
    with SessionLocal() as db:
        sessions = db.scalars(select(LiveSession).where(LiveSession.status == SessionStatus.ENDED.value, LiveSession.ended_at.is_not(None))).all()
        for session in sessions:
            elapsed = (now - (_aware(session.ended_at) or now)).total_seconds() / 3600
            items: list[tuple[int, bool]] = []
            for hours in settings.refund_offsets:
                if elapsed >= hours and not db.scalar(select(RefundSnapshot.id).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == snapshot_type(hours))):
                    items.append((hours, False))
            if elapsed >= settings.final_snapshot_after_hours and not db.scalar(select(RefundSnapshot.id).where(RefundSnapshot.session_id == session.id, RefundSnapshot.snapshot_type == "FINAL")):
                items.append((settings.final_snapshot_after_hours, True))
            if items:
                due[session.id] = items

    for session_id, items in due.items():
        if settings.data_provider.upper() == "TIKTOK":
            try:
                await sync_session(session_id, record_live_core=False, record_metric=False)
            except Exception as exc:
                with SessionLocal() as db:
                    session = db.get(LiveSession, session_id)
                    if session and not _recent_alert_exists(db, session.channel_id, "REFUND_SYNC_ERROR"):
                        create_alert(db, "REFUND_SYNC_ERROR", "REFUND SYNC ERROR", str(exc), severity="WARNING", session_id=session_id, channel_id=session.channel_id)
                        db.commit()
        with SessionLocal() as db:
            session = db.get(LiveSession, session_id)
            if not session:
                continue
            created = []
            for hours, final in items:
                created.append(refresh_refund_snapshot(db, session, hours, final=final).snapshot_type)
            db.commit()
        await manager.broadcast("refund.updated", {"session_id": session_id, "snapshots": created})
