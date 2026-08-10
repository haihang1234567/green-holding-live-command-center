from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import LiveSession, Order, RefundSnapshot
from app.services.kpi import SNAPSHOT_HOURS
from app.services.alerts import evaluate_refund_alert

def build_refund_snapshot(db:Session,session:LiveSession,snapshot_type:str)->RefundSnapshot:
    existing=db.query(RefundSnapshot).filter_by(session_id=session.id,snapshot_type=snapshot_type).first()
    if existing:return existing
    refund=int(db.query(func.coalesce(func.sum(Order.refund_amount),0)).filter(Order.live_session_id==session.id).scalar() or 0)
    cancelled=int(db.query(func.coalesce(func.sum(Order.cancelled_amount),0)).filter(Order.live_session_id==session.id).scalar() or 0)
    cancelled_orders=int(db.query(func.count(Order.id)).filter(Order.live_session_id==session.id,Order.order_status=="CANCELLED").scalar() or 0)
    original=int(session.current_gmv or session.initial_gmv or 0);loss=refund+cancelled;rate=round(loss/original*100,2) if original else 0.0
    snap=RefundSnapshot(session_id=session.id,snapshot_time=datetime.now(timezone.utc),hours_after_live=SNAPSHOT_HOURS[snapshot_type],snapshot_type=snapshot_type,original_gmv=original,refund_amount=refund,cancelled_amount=cancelled,refund_cancel_rate=rate,net_revenue=max(original-loss,0),total_orders=int(session.current_orders or 0),cancelled_orders=cancelled_orders)
    db.add(snap);db.commit();db.refresh(snap);evaluate_refund_alert(db,snap);return snap

def create_due_snapshots(db:Session):
    now=datetime.now(timezone.utc);ended=db.query(LiveSession).filter(LiveSession.status=="ENDED",LiveSession.ended_at.isnot(None)).all()
    for session in ended:
        end=session.ended_at if session.ended_at.tzinfo else session.ended_at.replace(tzinfo=timezone.utc);elapsed=(now-end).total_seconds()/3600
        for st,hours in SNAPSHOT_HOURS.items():
            if st!="FINAL" and elapsed>=float(hours or 0):build_refund_snapshot(db,session,st)
        if elapsed>=72:build_refund_snapshot(db,session,"FINAL")
