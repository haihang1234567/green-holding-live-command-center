from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import LiveSession, Order, RefundSnapshot

SNAPSHOT_ORDER = ["T0", "T1H", "T3H", "T6H", "T12H", "T24H", "T48H", "FINAL"]
SNAPSHOT_HOURS = {"T0": 0, "T1H": 1, "T3H": 3, "T6H": 6, "T12H": 12, "T24H": 24, "T48H": 48, "FINAL": None}


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def session_metrics(session: LiveSession, refund_snapshot: RefundSnapshot | None = None) -> dict:
    gmv = int(session.current_gmv or 0)
    orders = int(session.current_orders or 0)
    ads = int(session.current_ads_spend or 0)
    attributed = int(session.attributed_ads_revenue or 0)
    net = int(refund_snapshot.net_revenue) if refund_snapshot else gmv
    refund_rate = float(refund_snapshot.refund_cancel_rate) if refund_snapshot else 0.0
    end = _aware(session.ended_at) if session.ended_at else datetime.now(timezone.utc)
    started = _aware(session.started_at)
    hours = max((end - started).total_seconds() / 3600, 1 / 60)
    return {
        "gmv": gmv,
        "orders": orders,
        "ads_spend": ads,
        "aov": round(safe_div(gmv, orders)),
        "ads_gmv_pct": round(safe_div(ads, gmv) * 100, 2),
        "roas": round(safe_div(attributed or gmv, ads), 2),
        "net_revenue": net,
        "refund_rate": round(refund_rate, 2),
        "gmv_per_hour": round(safe_div(gmv, hours)),
        "orders_per_hour": round(safe_div(orders, hours), 1),
        "duration_seconds": int((end - started).total_seconds()),
    }


def get_refund_snapshot(db: Session, session_id: int, snapshot_type: str) -> RefundSnapshot | None:
    return db.query(RefundSnapshot).filter(RefundSnapshot.session_id == session_id, RefundSnapshot.snapshot_type == snapshot_type).first()


def top_skus(db: Session, session_id: int, limit: int = 5) -> list[dict]:
    rows = (
        db.query(Order.sku_id, Order.product_name, func.sum(Order.payment_amount).label("revenue"), func.sum(Order.quantity).label("qty"))
        .filter(Order.live_session_id == session_id)
        .group_by(Order.sku_id, Order.product_name)
        .order_by(func.sum(Order.payment_amount).desc())
        .limit(limit)
        .all()
    )
    return [{"sku_id": r.sku_id or "N/A", "product_name": r.product_name or "Chưa có dữ liệu", "revenue": int(r.revenue or 0), "quantity": int(r.qty or 0)} for r in rows]
