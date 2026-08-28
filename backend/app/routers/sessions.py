from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..attribution import override_serialized_session, session_attribution_summary
from ..database import get_db
from ..config import get_settings
from ..live_models import LiveCoreSnapshot
from ..models import LiveMetricSnapshot, LiveSession, RefundSnapshot, User, UserRole
from ..security import get_current_user
from ..services import serialize_session

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()


@router.get("")
def list_sessions(
    status: str | None = Query(default=None),
    team_id: int | None = Query(default=None),
    channel_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(LiveSession).options(joinedload(LiveSession.channel), joinedload(LiveSession.team)).where(LiveSession.channel_id.in_(settings.active_channel_ids))
    if status:
        query = query.where(LiveSession.status == status.upper())
    if user.role == UserRole.TEAM.value:
        query = query.where(LiveSession.team_id == user.team_id)
    elif team_id:
        query = query.where(LiveSession.team_id == team_id)
    if channel_id:
        query = query.where(LiveSession.channel_id == channel_id)
    vietnam = ZoneInfo("Asia/Ho_Chi_Minh")
    if date_from:
        start = datetime.combine(date_from, datetime.min.time(), tzinfo=vietnam).astimezone(timezone.utc)
        query = query.where(LiveSession.started_at >= start)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=vietnam).astimezone(timezone.utc)
        query = query.where(LiveSession.started_at < end)
    rows = db.scalars(query.order_by(LiveSession.started_at.desc()).limit(limit)).unique().all()
    ids = [row.id for row in rows]
    snapshot_meta = {}
    if ids:
        snapshot_meta = {
            session_id: {"snapshot_count": int(count or 0), "latest_snapshot_at": latest}
            for session_id, count, latest in db.execute(
                select(
                    LiveMetricSnapshot.session_id,
                    func.count(LiveMetricSnapshot.id),
                    func.max(LiveMetricSnapshot.timestamp),
                )
                .where(LiveMetricSnapshot.session_id.in_(ids))
                .group_by(LiveMetricSnapshot.session_id)
            ).all()
        }
    output = []
    for row in rows:
        payload = override_serialized_session(db, serialize_session(db, row))
        payload.update(snapshot_meta.get(row.id, {"snapshot_count": 0, "latest_snapshot_at": None}))
        output.append(payload)
    return output


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.scalar(
        select(LiveSession)
        .options(joinedload(LiveSession.channel), joinedload(LiveSession.team))
        .where(LiveSession.id == session_id,LiveSession.channel_id.in_(settings.active_channel_ids))
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
