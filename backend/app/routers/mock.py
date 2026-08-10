from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..database import get_db
from ..models import Channel, LiveSession, SessionStatus, Team
from ..realtime import manager
from ..security import require_admin
from ..services import add_mock_ads, add_mock_orders, apply_mock_refund_or_cancel, create_metric_snapshot, serialize_session, start_session, stop_session

settings = get_settings()
router = APIRouter(prefix="/mock", tags=["mock"])


class MockStart(BaseModel):
    team_id: int
    shift: str = "CA_SANG"


class MockAmount(BaseModel):
    amount: float = Field(gt=0)


class MockOrders(BaseModel):
    count: int = Field(default=1, ge=1, le=100)


def _ensure_mock():
    if settings.data_provider.upper() != "MOCK":
        raise HTTPException(409, "Mock Control bị khóa khi DATA_PROVIDER không phải MOCK")


def _active(db: Session, channel_id: int | None = None, session_id: int | None = None) -> LiveSession:
    query = select(LiveSession).options(joinedload(LiveSession.channel), joinedload(LiveSession.team)).where(LiveSession.status == SessionStatus.LIVE.value)
    if session_id:
        query = query.where(LiveSession.id == session_id)
    if channel_id:
        query = query.where(LiveSession.channel_id == channel_id)
    session = db.scalar(query)
    if not session:
        raise HTTPException(404, "Không có phiên LIVE đang chạy")
    return session


@router.post("/channels/{channel_id}/start")
async def start(channel_id: int, payload: MockStart, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    channel = db.get(Channel, channel_id)
    team = db.get(Team, payload.team_id)
    if not channel or not team:
        raise HTTPException(404, "Không tìm thấy kênh/team")
    channel.mock_is_live = True
    session = start_session(db, channel, team, payload.shift.upper(), "MOCK")
    db.commit()
    await manager.broadcast("channel.status", {"channel_id": channel.id, "status": "LIVE", "session_id": session.id})
    return serialize_session(db, session)


@router.post("/channels/{channel_id}/stop")
async def stop(channel_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    session = _active(db, channel_id=channel_id)
    session.channel.mock_is_live = False
    stop_session(db, session)
    db.commit()
    await manager.broadcast("channel.status", {"channel_id": channel_id, "status": "OFFLINE", "session_id": session.id})
    return serialize_session(db, session)


@router.post("/sessions/{session_id}/orders")
async def orders(session_id: int, payload: MockOrders, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    session = _active(db, session_id=session_id)
    add_mock_orders(db, session, payload.count)
    db.flush()
    create_metric_snapshot(db, session)
    db.commit()
    await manager.broadcast("metrics.updated", {"session_id": session.id})
    return serialize_session(db, session)


@router.post("/sessions/{session_id}/gmv")
async def gmv(session_id: int, payload: MockAmount, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    session = _active(db, session_id=session_id)
    add_mock_orders(db, session, count=1, gmv_increment=payload.amount)
    db.flush()
    create_metric_snapshot(db, session)
    db.commit()
    await manager.broadcast("metrics.updated", {"session_id": session.id})
    return serialize_session(db, session)


@router.post("/sessions/{session_id}/ads")
async def ads(session_id: int, payload: MockAmount, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    session = _active(db, session_id=session_id)
    add_mock_ads(db, session, payload.amount)
    db.flush()
    create_metric_snapshot(db, session)
    db.commit()
    await manager.broadcast("metrics.updated", {"session_id": session.id})
    return serialize_session(db, session)


@router.post("/sessions/{session_id}/refund")
async def refund(session_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    session = _active(db, session_id=session_id)
    row = apply_mock_refund_or_cancel(db, session, "refund")
    if not row:
        raise HTTPException(409, "Không còn đơn phù hợp để hoàn")
    create_metric_snapshot(db, session)
    db.commit()
    await manager.broadcast("metrics.updated", {"session_id": session.id})
    return {"ok": True, "order_id": row.parent_order_id or row.order_id}


@router.post("/sessions/{session_id}/cancel")
async def cancel(session_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    _ensure_mock()
    session = _active(db, session_id=session_id)
    row = apply_mock_refund_or_cancel(db, session, "cancel")
    if not row:
        raise HTTPException(409, "Không còn đơn phù hợp để hủy")
    create_metric_snapshot(db, session)
    db.commit()
    await manager.broadcast("metrics.updated", {"session_id": session.id})
    return {"ok": True, "order_id": row.parent_order_id or row.order_id}
