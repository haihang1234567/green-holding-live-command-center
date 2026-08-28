from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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
from .models import AdsSnapshot, Alert, AppSetting, Channel, LiveMetricSnapshot, LiveSession, Order, RefundSnapshot, SessionStatus, Team
from .providers import TikTokShopProvider
from .realtime import manager
from .services import create_alert, create_metric_snapshot, local_shift, snapshot_type, start_session, stop_session, sync_normalized_order
from .tiktok_analytics import get_best_live_metrics, live_performance_values

settings = get_settings()
monitor_state: dict[str, Any] = {"last_cycle_at": None, "last_cycle_duration_ms": None, "channels": {}}
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
LIVE_STATES = {"LIVE", "ONGOING", "IN_PROGRESS", "STREAMING"}
ENDED_STATES = {"ENDED", "END", "FINISHED", "COMPLETED", "OFFLINE"}


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


def _safe_error(exc: Exception) -> str:
    """Return a useful error without leaking signed TikTok request URLs."""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return f"TikTok API HTTP {status_code}" if status_code else type(exc).__name__


def _api_team(db) -> Team:
    """Internal owner for API sessions; no operator scheduling is required."""
    team = db.scalar(select(Team).where(Team.name == "TikTok API"))
    if not team:
        team = Team(name="TikTok API", target_gmv=0)
        db.add(team)
        db.flush()
    return team


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


def _epoch_datetime(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        epoch = int(value)
        return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch > 0 else None
    except (TypeError, ValueError, OSError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return _aware(parsed)
        except (TypeError, ValueError):
            return None


def _performance_report_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("live_id") or item.get("live_room_id") or "").strip()


def _performance_report_state(item: dict[str, Any], started: datetime, ended: datetime | None) -> str:
    raw_state = str(item.get("status") or item.get("live_status") or "").strip().upper()
    if raw_state in LIVE_STATES:
        return SessionStatus.LIVE.value
    if ended or raw_state in ENDED_STATES:
        return SessionStatus.ENDED.value
    # TikTok may omit status/end_time for an in-progress report. Bound the
    # inference so an incomplete historical row cannot stay LIVE forever.
    age = datetime.now(timezone.utc) - started
    return SessionStatus.LIVE.value if timedelta(minutes=-5) <= age <= timedelta(hours=36) else SessionStatus.ENDED.value


def _performance_report_end(item: dict[str, Any], started: datetime) -> datetime | None:
    ended = _epoch_datetime(item.get("end_time"))
    if ended:
        return ended
    duration = item.get("duration_seconds") or item.get("duration")
    try:
        seconds = int(float(duration))
    except (TypeError, ValueError):
        return None
    return started + timedelta(seconds=seconds) if seconds > 0 else None


def _ingest_performance_report(
    db,
    channel: Channel,
    item: dict[str, Any],
    *,
    capture_unchanged: bool = False,
) -> int | None:
    """Upsert one TikTok LIVE report into permanent session history."""
    external_id = _performance_report_id(item)
    started = _epoch_datetime(item.get("start_time"))
    if not external_id or not started:
        return None

    ended = _performance_report_end(item, started)
    report_status = _performance_report_state(item, started, ended)
    session_code = f"TTS-{channel.id}-{external_id}"[:64]
    session = db.scalar(
        select(LiveSession)
        .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
        .where(LiveSession.session_code == session_code)
    )
    if not session:
        # Reconcile a provisional AUTO_API row created while TikTok was LIVE.
        # Never merge two analytics reports merely because they started close.
        session = db.scalar(
            select(LiveSession)
            .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
            .where(
                LiveSession.channel_id == channel.id,
                LiveSession.source == "AUTO_API",
                LiveSession.started_at >= started - timedelta(minutes=15),
                LiveSession.started_at <= started + timedelta(minutes=15),
            )
            .order_by(LiveSession.started_at.desc())
            .limit(1)
        )
    if not session:
        team = _api_team(db)
        session = LiveSession(
            session_code=session_code,
            channel_id=channel.id,
            team_id=team.id,
            shift=local_shift(started),
            started_at=started,
            ended_at=ended,
            status=report_status,
            source="TIKTOK_ANALYTICS",
        )
        db.add(session)
        db.flush()
        session.channel = channel
        session.team = team
    else:
        session.session_code = session_code
        session.started_at = started
        session.ended_at = ended
        session.status = report_status
        if session.source != "MOCK":
            session.source = "TIKTOK_ANALYTICS"

    # Only one LIVE row per channel is valid. A new TikTok live_id closes any
    # stale provisional/history row at the new session boundary.
    if report_status == SessionStatus.LIVE.value:
        stale_rows = db.scalars(
            select(LiveSession).where(
                LiveSession.channel_id == channel.id,
                LiveSession.status == SessionStatus.LIVE.value,
                LiveSession.id != session.id,
            )
        ).all()
        for stale in stale_rows:
            stale.status = SessionStatus.ENDED.value
            stale.ended_at = stale.ended_at or started
        channel.status = SessionStatus.LIVE.value
    elif not db.scalar(
        select(LiveSession.id).where(
            LiveSession.channel_id == channel.id,
            LiveSession.status == SessionStatus.LIVE.value,
            LiveSession.id != session.id,
        ).limit(1)
    ):
        channel.status = SessionStatus.OFFLINE.value

    values = live_performance_values(item)
    raw_json = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    previous = db.scalar(
        select(LiveCoreSnapshot)
        .where(LiveCoreSnapshot.session_id == session.id)
        .order_by(LiveCoreSnapshot.captured_at.desc())
        .limit(1)
    )
    if capture_unchanged or not previous or previous.raw_json != raw_json:
        db.add(
            LiveCoreSnapshot(
                session_id=session.id,
                channel_id=channel.id,
                captured_at=datetime.now(timezone.utc),
                gmv=normalized_live_metric(values, "gmv"),
                orders=normalized_live_metric(values, "orders", integer=True),
                paid_orders=normalized_live_metric(values, "paid_orders", integer=True),
                buyers=normalized_live_metric(values, "buyers", integer=True),
                current_viewers=None,
                peak_viewers=None,
                product_views=None,
                ctr=None,
                comments=None,
                shares=None,
                avg_watch_seconds=None,
                raw_json=raw_json,
            )
        )
        db.flush()
        _record_live_metric_snapshot(db, session)
    if report_status == SessionStatus.ENDED.value and ended and not db.scalar(
        select(RefundSnapshot.id).where(
            RefundSnapshot.session_id == session.id,
            RefundSnapshot.snapshot_type == "T+0",
        ).limit(1)
    ):
        refresh_refund_snapshot(db, session, 0)
    return session.id


def _ingest_performance_reports(
    db,
    channel: Channel,
    reports: list[dict[str, Any]],
    *,
    active_report_id: str | None = None,
) -> dict[str, Any]:
    """Persist every report returned by TikTok, idempotently by live_id."""
    session_ids: list[int] = []
    seen: set[str] = set()
    ordered = sorted(
        (item for item in reports if isinstance(item, dict)),
        key=lambda item: _epoch_datetime(item.get("start_time")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for item in ordered:
        external_id = _performance_report_id(item)
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        session_id = _ingest_performance_report(
            db,
            channel,
            item,
            capture_unchanged=bool(active_report_id and external_id == active_report_id),
        )
        if session_id:
            session_ids.append(session_id)
    return {"reports_seen": len(seen), "sessions_saved": len(session_ids), "session_ids": session_ids}


def _history_setting_key(channel_id: int) -> str:
    return f"channel_{channel_id}_live_history_backfill_at"


async def _backfill_live_history(channel_id: int) -> dict[str, Any]:
    """Backfill recent LIVE history once per configured refresh period."""
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            return {"ok": False, "reason": "channel_not_found"}
        setting = db.get(AppSetting, _history_setting_key(channel_id))
        last_run = _epoch_datetime(setting.value) if setting else None
        refresh_after = timedelta(hours=max(1, settings.live_history_refresh_hours))
        if last_run and datetime.now(timezone.utc) - last_run < refresh_after:
            return {"ok": True, "skipped": True}
        client, _ = shop_client(channel)

    end_date = datetime.now(VN_TZ).date() + timedelta(days=1)
    start_date = end_date - timedelta(days=max(1, settings.live_history_lookback_days))
    cursor = start_date
    reports_by_id: dict[str, dict[str, Any]] = {}
    # Small date chunks stay within TikTok Analytics range limits and make a
    # partial retry inexpensive if one request fails.
    while cursor < end_date:
        chunk_end = min(cursor + timedelta(days=7), end_date)
        rows = await client.get_shop_live_sessions(channel, cursor.isoformat(), chunk_end.isoformat())
        for item in rows:
            external_id = _performance_report_id(item) if isinstance(item, dict) else ""
            if external_id:
                reports_by_id[external_id] = item
        cursor = chunk_end

    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            return {"ok": False, "reason": "channel_not_found"}
        result = _ingest_performance_reports(db, channel, list(reports_by_id.values()))
        now_text = datetime.now(timezone.utc).isoformat()
        setting = db.get(AppSetting, _history_setting_key(channel_id))
        if setting:
            setting.value = now_text
        else:
            db.add(AppSetting(key=_history_setting_key(channel_id), value=now_text))
        db.commit()
    return {"ok": True, "skipped": False, **result}


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
        shop, profile = shop_client(channel)
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

        # Affiliate is optional and requires a separate approved permission.
        attribution_counts: dict[str, int] = {}
        affiliate_ok = False
        if settings.enable_affiliate_attribution:
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
                        f"{channel.name}: {_safe_error(exc)}",
                        severity="WARNING",
                        session_id=session.id,
                        channel_id=channel.id,
                    )

        raw_returns = await shop.get_returns(channel, max(started, now - timedelta(days=8)), now)
        return_count = _apply_returns(db, channel, raw_returns)

        ads_ok = False
        if profile.ads_access_token and profile.advertiser_id:
            ads, _ = ads_client(channel)
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
                    create_alert(db, "ADS_SYNC_WARNING", "ADS SYNC WARNING", f"{channel.name}: {_safe_error(exc)}", severity="WARNING", session_id=session.id, channel_id=channel.id)

        # Seller-authorized Shop LIVE Performance is the primary KPI source.
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
                    create_alert(db, "LIVE_METRIC_WARNING", "LIVE METRIC WARNING", f"{channel.name}: {_safe_error(exc)}", severity="WARNING", session_id=session.id, channel_id=channel.id)

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
        ids = list(db.scalars(select(Channel.id).where(Channel.id.in_(settings.active_channel_ids),Channel.polling_enabled.is_(True)).order_by(Channel.id)).all())

    for channel_id in ids:
        signal: dict[str, Any] = {"status": "UNKNOWN"}
        session_id: int | None = None
        history_result: dict[str, Any] | None = None
        try:
            history_result = await _backfill_live_history(channel_id)
        except Exception as exc:
            history_result = {"ok": False, "error": _safe_error(exc)}
        with SessionLocal() as db:
            channel = db.get(Channel, channel_id)
            if not channel:
                continue
            profile = profile_for_channel(channel)
            state: dict[str, Any] = {"shop": profile.name, "channel_id": channel.id, "checked_at": datetime.now(timezone.utc).isoformat(), "history": history_result}
            try:
                signal = await get_live_signal(channel)
                state.update(signal=signal["status"], live_room_id=signal.get("live_room_id"), error=None)
                raw_signal = signal.get("raw") or {}
                reports = raw_signal.get("sessions") or []
                latest_report = raw_signal.get("latest_session")
                if not reports and isinstance(latest_report, dict):
                    reports = [latest_report]
                ingest_result = _ingest_performance_reports(
                    db,
                    channel,
                    reports,
                    active_report_id=signal.get("live_room_id") if signal["status"] == "LIVE" else None,
                )
                state["history_ingest"] = ingest_result
                db.commit()
            except Exception as exc:
                state.update(signal="UNKNOWN", error=_safe_error(exc))
                if not _recent_alert_exists(db, channel.id, "LIVE_STATUS_ERROR"):
                    create_alert(db, "LIVE_STATUS_ERROR", "LIVE STATUS ERROR", f"{channel.name}: {_safe_error(exc)}", severity="WARNING", channel_id=channel.id)
                db.commit()
                monitor_state["channels"][str(channel.id)] = state
                continue

            active = db.scalar(
                select(LiveSession)
                .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
                .where(LiveSession.channel_id == channel.id, LiveSession.status == SessionStatus.LIVE.value)
                .order_by(LiveSession.started_at.desc())
                .limit(1)
            )
            session_id = active.id if active else None

            if signal["status"] == "LIVE" and not active:
                shift = local_shift()
                team = _api_team(db)
                active = start_session(db, channel, team, shift, "AUTO_API")
                _set_active_room(db, channel.id, signal.get("live_room_id"))
                db.commit()
                session_id = active.id
                events.append({"channel_id": channel.id, "channel_name": channel.name, "shop": profile.name, "status": "LIVE", "session_id": session_id})

            elif signal["status"] == "OFFLINE" and active:
                # Close every stale LIVE row, not only whichever row happens
                # to be returned first by PostgreSQL.
                active_ids = list(db.scalars(
                    select(LiveSession.id).where(
                        LiveSession.channel_id == channel.id,
                        LiveSession.status == SessionStatus.LIVE.value,
                    )
                ).all())
                session_id = active_ids[-1] if active_ids else None
                db.commit()
                for closing_id in active_ids:
                    try:
                        await sync_session(closing_id)
                    except Exception as exc:
                        with SessionLocal() as adb:
                            if not _recent_alert_exists(adb, channel.id, "FINAL_SYNC_WARNING"):
                                create_alert(adb, "FINAL_SYNC_WARNING", "FINAL SYNC WARNING", f"{channel.name}: {_safe_error(exc)}", severity="WARNING", session_id=closing_id, channel_id=channel.id)
                                adb.commit()
                    with SessionLocal() as cdb:
                        closing = cdb.scalar(
                            select(LiveSession)
                            .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
                            .where(LiveSession.id == closing_id)
                        )
                        if closing and closing.status == SessionStatus.LIVE.value:
                            stop_session(cdb, closing)
                            refresh_refund_snapshot(cdb, closing, 0)
                            cdb.commit()
                with SessionLocal() as cdb:
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
                        create_alert(adb, "SHOP_SYNC_ERROR", "SHOP SYNC ERROR", _safe_error(exc), severity="WARNING", session_id=session_id, channel_id=channel_id)
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
        sessions = db.scalars(select(LiveSession).where(LiveSession.status == SessionStatus.ENDED.value,LiveSession.channel_id.in_(settings.active_channel_ids),LiveSession.ended_at.is_not(None))).all()
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
                        create_alert(db, "REFUND_SYNC_ERROR", "REFUND SYNC ERROR", _safe_error(exc), severity="WARNING", session_id=session_id, channel_id=session.channel_id)
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
