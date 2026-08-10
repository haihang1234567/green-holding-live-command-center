from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..attribution import override_serialized_session, session_attribution_summary
from ..database import get_db
from ..live_models import LiveCoreSnapshot
from ..models import LiveMetricSnapshot, LiveSession, RefundSnapshot, User, UserRole
from ..security import get_current_user
from ..services import serialize_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def list_sessions(
    status: str | None = Query(default=None),
    team_id: int | None = Query(default=None),
    channel_id: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(LiveSession).options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
    if status:
        query = query.where(LiveSession.status == status.upper())
    if user.role == UserRole.TEAM.value:
        query = query.where(LiveSession.team_id == user.team_id)
    elif team_id:
        query = query.where(LiveSession.team_id == team_id)
    if channel_id:
        query = query.where(LiveSession.channel_id == channel_id)
    rows = db.scalars(query.order_by(LiveSession.started_at.desc()).limit(limit)).unique().all()
    return [override_serialized_session(db, serialize_session(db, row)) for row in rows]


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.scalar(
        select(LiveSession)
        .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
        .where(LiveSession.id == session_id)
    )
    if not session:
        raise HTTPException(404, "Không tìm thấy phiên LIVE")
    if user.role == UserRole.TEAM.value and user.team_id != session.team_id:
        raise HTTPException(403, "Không có quyền xem phiên này")

    metrics = db.scalars(
        select(LiveMetricSnapshot).where(LiveMetricSnapshot.session_id == session_id).order_by(LiveMetricSnapshot.timestamp)
    ).all()
    core = db.scalars(
        select(LiveCoreSnapshot).where(LiveCoreSnapshot.session_id == session_id).order_by(LiveCoreSnapshot.captured_at)
    ).all()
    refunds = db.scalars(
        select(RefundSnapshot).where(RefundSnapshot.session_id == session_id).order_by(RefundSnapshot.hours_after_live)
    ).all()
    latest = core[-1] if core else None
    base = override_serialized_session(db, serialize_session(db, session))
    return {
        **base,
        "timeline": [
            {
                "timestamp": row.timestamp,
                "gmv": float(row.gmv or 0),
                "orders": row.orders,
                "ads_spend": float(row.ads_spend or 0),
                "current_viewers": row.current_viewers,
            }
            for row in metrics
        ],
        "live_core_latest": None if not latest else {
            "captured_at": latest.captured_at,
            "gmv": float(latest.gmv) if latest.gmv is not None else None,
            "orders": latest.orders,
            "paid_orders": latest.paid_orders,
            "buyers": latest.buyers,
            "current_viewers": latest.current_viewers,
            "peak_viewers": latest.peak_viewers,
            "product_views": latest.product_views,
            "ctr": latest.ctr,
            "comments": latest.comments,
            "shares": latest.shares,
            "avg_watch_seconds": latest.avg_watch_seconds,
        },
        "attribution": session_attribution_summary(db, session_id),
        "refund_snapshots": [
            {
                "id": row.id,
                "snapshot_type": row.snapshot_type,
                "hours_after_live": row.hours_after_live,
                "snapshot_time": row.snapshot_time,
                "original_gmv": float(row.original_gmv or 0),
                "refund_amount": float(row.refund_amount or 0),
                "cancelled_amount": float(row.cancelled_amount or 0),
                "refund_cancel_rate": row.refund_cancel_rate,
                "net_revenue": float(row.net_revenue or 0),
                "total_orders": row.total_orders,
                "cancelled_orders": row.cancelled_orders,
            }
            for row in refunds
        ],
    }
