from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Channel, LiveMetricSnapshot, LiveSession, RefundSnapshot, SessionStatus, Team, User, UserRole
from ..realtime import manager
from ..security import get_current_user, require_admin
from ..services import serialize_session, start_session, stop_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionPayload(BaseModel):
    channel_id: int
    team_id: int
    shift: str = "CA_SANG"


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
    return [serialize_session(db, x) for x in rows]


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = db.scalar(
        select(LiveSession).options(joinedload(LiveSession.channel), joinedload(LiveSession.team)).where(LiveSession.id == session_id)
    )
    if not session:
        raise HTTPException(404, "Không tìm thấy phiên LIVE")
    if user.role == UserRole.TEAM.value and user.team_id != session.team_id:
        raise HTTPException(403, "Không có quyền xem phiên này")
    metrics = db.scalars(select(LiveMetricSnapshot).where(LiveMetricSnapshot.session_id == session_id).order_by(LiveMetricSnapshot.timestamp)).all()
    refunds = db.scalars(select(RefundSnapshot).where(RefundSnapshot.session_id == session_id).order_by(RefundSnapshot.hours_after_live)).all()
    return {
        **serialize_session(db, session),
        "timeline": [{"timestamp": x.timestamp, "gmv": float(x.gmv or 0), "orders": x.orders, "ads_spend": float(x.ads_spend or 0), "current_viewers": x.current_viewers} for x in metrics],
        "refund_snapshots": [{"id": x.id, "snapshot_type": x.snapshot_type, "hours_after_live": x.hours_after_live, "snapshot_time": x.snapshot_time, "original_gmv": float(x.original_gmv or 0), "refund_amount": float(x.refund_amount or 0), "cancelled_amount": float(x.cancelled_amount or 0), "refund_cancel_rate": x.refund_cancel_rate, "net_revenue": float(x.net_revenue or 0), "total_orders": x.total_orders, "cancelled_orders": x.cancelled_orders} for x in refunds],
    }


@router.post("/manual/start")
async def manual_start(payload: StartSessionPayload, db: Session = Depends(get_db), _=Depends(require_admin)):
    channel = db.get(Channel, payload.channel_id)
    team = db.get(Team, payload.team_id)
    if not channel or not team:
        raise HTTPException(404, "Không tìm thấy channel/team")
    channel.mock_is_live = True
    session = start_session(db, channel, team, payload.shift.upper(), "MANUAL")
    db.commit()
    await manager.broadcast("channel.status", {"channel_id": channel.id, "status": "LIVE", "session_id": session.id})
    return serialize_session(db, session)


@router.post("/{session_id}/stop")
async def manual_stop(session_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    session = db.scalar(select(LiveSession).options(joinedload(LiveSession.channel), joinedload(LiveSession.team)).where(LiveSession.id == session_id))
    if not session:
        raise HTTPException(404, "Không tìm thấy phiên LIVE")
    session.channel.mock_is_live = False
    stop_session(db, session)
    db.commit()
    await manager.broadcast("channel.status", {"channel_id": session.channel_id, "status": "OFFLINE", "session_id": session.id})
    return serialize_session(db, session)
