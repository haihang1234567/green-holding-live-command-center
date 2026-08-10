import random
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Channel, LiveSession, Order, LiveMetricSnapshot, AdsSnapshot, Alert
from app.services.snapshot import build_refund_snapshot
from app.services.alerts import create_alert, evaluate_session_alerts

PRODUCTS = [
    ("P001", "SKU001", "Sản phẩm A", 79000),
    ("P002", "SKU002", "Sản phẩm B", 129000),
    ("P003", "SKU003", "Sản phẩm C", 59000),
    ("P004", "SKU004", "Sản phẩm D", 99000),
]


def _snapshot(db: Session, session: LiveSession):
    db.add(LiveMetricSnapshot(session_id=session.id, gmv=session.current_gmv, orders=session.current_orders, ads_spend=session.current_ads_spend, buyers=session.buyers, product_quantity=session.product_quantity))
    roas = round((session.attributed_ads_revenue or session.current_gmv) / session.current_ads_spend, 2) if session.current_ads_spend else 0
    db.add(AdsSnapshot(live_session_id=session.id, spend=session.current_ads_spend, orders=session.current_orders, gross_revenue=session.attributed_ads_revenue, roas=roas))
    db.commit()


def start_live(db: Session, channel_id: int, team_id: int, shift: str):
    channel = db.get(Channel, channel_id)
    if not channel:
        raise ValueError("Channel not found")
    existing = db.query(LiveSession).filter(LiveSession.channel_id == channel_id, LiveSession.status == "LIVE").first()
    if existing:
        return existing
    code = f"S{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-C{channel_id}-T{team_id}"
    session = LiveSession(session_code=code, channel_id=channel_id, team_id=team_id, shift=shift.upper(), status="LIVE")
    channel.status = "LIVE"
    db.add(session)
    db.commit()
    db.refresh(session)
    create_alert(db, "LIVE_STARTED", "LIVE STARTED", f"{channel.name} đã bắt đầu LIVE", session.id, "INFO")
    _snapshot(db, session)
    return session


def stop_live(db: Session, channel_id: int):
    channel = db.get(Channel, channel_id)
    session = db.query(LiveSession).filter(LiveSession.channel_id == channel_id, LiveSession.status == "LIVE").first()
    if not session:
        raise ValueError("No LIVE session")
    session.status = "ENDED"
    session.ended_at = datetime.now(timezone.utc)
    session.initial_gmv = session.current_gmv
    if channel:
        channel.status = "OFFLINE"
    db.commit()
    build_refund_snapshot(db, session, "T0")
    create_alert(db, "LIVE_ENDED", "LIVE ENDED", f"Phiên {session.session_code} đã kết thúc", session.id, "INFO")
    return session


def add_orders(db: Session, session_id: int, count: int = 1):
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("Session not found")
    for _ in range(max(1, min(count, 100))):
        product_id, sku_id, name, price = random.choice(PRODUCTS)
        qty = random.choice([1, 1, 1, 2, 3])
        amount = price * qty
        order = Order(order_id=f"MOCK-{session.id}-{datetime.now(timezone.utc).timestamp()}-{random.randint(1000,9999)}", live_session_id=session.id, sku_id=sku_id, product_id=product_id, product_name=name, quantity=qty, amount=amount, payment_amount=amount, order_status="PAID")
        db.add(order)
        session.current_gmv += amount
        session.current_orders += 1
        session.buyers += 1
        session.product_quantity += qty
        session.attributed_ads_revenue += int(amount * random.uniform(0.55, 0.9))
    db.commit()
    _snapshot(db, session)
    evaluate_session_alerts(db, session)
    return session


def increase_gmv(db: Session, session_id: int, amount: int):
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("Session not found")
    session.current_gmv += max(0, amount)
    db.commit()
    _snapshot(db, session)
    return session


def add_ads(db: Session, session_id: int, amount: int):
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("Session not found")
    session.current_ads_spend += max(0, amount)
    db.commit()
    _snapshot(db, session)
    evaluate_session_alerts(db, session)
    return session


def cancel_random_order(db: Session, session_id: int):
    order = db.query(Order).filter(Order.live_session_id == session_id, Order.order_status == "PAID").order_by(Order.id.desc()).first()
    if not order:
        raise ValueError("No cancellable order")
    order.order_status = "CANCELLED"
    order.cancelled_amount = order.payment_amount
    order.cancellation_reason = "Mock cancellation"
    db.commit()
    return order


def refund_random_order(db: Session, session_id: int):
    order = db.query(Order).filter(Order.live_session_id == session_id, Order.order_status.in_(["PAID", "COMPLETED"]), Order.refund_amount == 0).order_by(Order.id.desc()).first()
    if not order:
        raise ValueError("No refundable order")
    order.order_status = "REFUNDED"
    order.refund_amount = order.payment_amount
    db.commit()
    return order


def auto_tick(db: Session):
    sessions = db.query(LiveSession).filter(LiveSession.status == "LIVE").all()
    for session in sessions:
        add_orders(db, session.id, random.randint(1, 3))
        if random.random() < 0.8:
            add_ads(db, session.id, random.randint(20_000, 120_000))
