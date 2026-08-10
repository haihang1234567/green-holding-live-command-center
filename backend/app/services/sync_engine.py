from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Channel, ChannelShiftAssignment, LiveSession, Order, LiveMetricSnapshot, AdsSnapshot
from app.providers.factory import providers
from app.services.alerts import create_alert, evaluate_session_alerts
from app.services.snapshot import build_refund_snapshot


def _assignment(db: Session, channel_id: int) -> ChannelShiftAssignment | None:
    hour = datetime.now().hour
    rows = db.query(ChannelShiftAssignment).filter_by(channel_id=channel_id, active=True).all()
    for row in rows:
        if row.start_hour < row.end_hour and row.start_hour <= hour < row.end_hour:
            return row
        if row.start_hour > row.end_hour and (hour >= row.start_hour or hour < row.end_hour):
            return row
    return rows[0] if rows else None


def _open_session(db: Session, channel: Channel, assignment: ChannelShiftAssignment) -> LiveSession:
    code = f"TT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-C{channel.id}-T{assignment.team_id}"
    s = LiveSession(session_code=code, channel_id=channel.id, team_id=assignment.team_id, shift=assignment.shift, status="LIVE")
    channel.status = "LIVE"
    db.add(s); db.commit(); db.refresh(s)
    create_alert(db, "LIVE_STARTED", "LIVE STARTED", f"{channel.name} đã bắt đầu LIVE", s.id, "INFO")
    return s


def _close_session(db: Session, channel: Channel, session: LiveSession):
    session.status = "ENDED"
    session.ended_at = datetime.now(timezone.utc)
    session.initial_gmv = session.current_gmv
    channel.status = "OFFLINE"
    db.commit()
    build_refund_snapshot(db, session, "T0")
    create_alert(db, "LIVE_ENDED", "LIVE ENDED", f"Phiên {session.session_code} đã kết thúc", session.id, "INFO")


def _sync_orders(db: Session, session: LiveSession, rows: list[dict]):
    changed = False
    for row in rows:
        oid = row.get("order_id")
        if not oid or db.query(Order).filter_by(order_id=str(oid)).first():
            continue
        amount = int(float(row.get("amount") or 0))
        status = str(row.get("status") or "UNKNOWN").upper()
        order = Order(order_id=str(oid), live_session_id=session.id, product_id=str(row.get("product_id") or "") or None, sku_id=str(row.get("sku_id") or "") or None, product_name=str(row.get("product_name") or "Chưa có dữ liệu"), quantity=int(row.get("quantity") or 1), amount=amount, payment_amount=amount, order_status=status)
        db.add(order)
        if status not in {"CANCELLED", "REFUNDED"}:
            session.current_gmv += amount
            session.current_orders += 1
            session.buyers += 1
            session.product_quantity += int(row.get("quantity") or 1)
        changed = True
    if changed:
        db.commit()


def poll_real_data(db: Session):
    shop, ads, live = providers()
    for channel in db.query(Channel).all():
        status = live.get_live_status(channel.external_channel_id)
        current = db.query(LiveSession).filter_by(channel_id=channel.id, status="LIVE").order_by(LiveSession.started_at.desc()).first()
        if status == "LIVE" and not current:
            assignment = _assignment(db, channel.id)
            if assignment:
                current = _open_session(db, channel, assignment)
        elif status == "OFFLINE" and current:
            _close_session(db, channel, current)
            current = None
        if not current:
            continue
        since = current.started_at.isoformat()
        try:
            _sync_orders(db, current, shop.get_orders(channel.external_channel_id, since))
        except Exception as exc:
            print("shop sync error", channel.id, exc)
        try:
            metrics = ads.get_metrics(channel.advertiser_id, since) or {}
            if metrics:
                current.current_ads_spend = int(float(metrics.get("spend") or current.current_ads_spend or 0))
                current.attributed_ads_revenue = int(float(metrics.get("gross_revenue") or current.attributed_ads_revenue or 0))
                db.commit()
        except Exception as exc:
            print("ads sync error", channel.id, exc)
        db.add(LiveMetricSnapshot(session_id=current.id, gmv=current.current_gmv, orders=current.current_orders, ads_spend=current.current_ads_spend, buyers=current.buyers, product_quantity=current.product_quantity))
        roas = (current.attributed_ads_revenue/current.current_ads_spend) if current.current_ads_spend else 0
        db.add(AdsSnapshot(live_session_id=current.id, spend=current.current_ads_spend, orders=current.current_orders, gross_revenue=current.attributed_ads_revenue, roas=roas))
        db.commit()
        evaluate_session_alerts(db, current)
