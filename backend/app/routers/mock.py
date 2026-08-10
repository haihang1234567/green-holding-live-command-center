from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db import get_db
from app.deps import require_admin
from app.schemas import MockStartRequest, MockChannelRequest, MockOrdersRequest, MockMoneyRequest, MockSessionRequest
from app.services import mock_engine
from app.services.realtime import manager
from app.services.snapshot import build_refund_snapshot
from app.models import LiveSession

router = APIRouter(prefix="/mock", tags=["mock"], dependencies=[Depends(require_admin)])


def _guard():
    if get_settings().data_provider.upper() != "MOCK": raise HTTPException(403, "Mock control is disabled while DATA_PROVIDER=TIKTOK")


async def _done(action: str, session_id: int | None = None):
    await manager.broadcast({"type": "DATA_UPDATED", "action": action, "session_id": session_id})
    return {"ok": True, "action": action, "session_id": session_id}


@router.post("/start-live")
async def start_live(payload: MockStartRequest, db: Session = Depends(get_db)):
    _guard()
    try: s = mock_engine.start_live(db, payload.channel_id, payload.team_id, payload.shift)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("START_LIVE", s.id)


@router.post("/stop-live")
async def stop_live(payload: MockChannelRequest, db: Session = Depends(get_db)):
    _guard()
    try: s = mock_engine.stop_live(db, payload.channel_id)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("STOP_LIVE", s.id)


@router.post("/add-orders")
async def add_orders(payload: MockOrdersRequest, db: Session = Depends(get_db)):
    _guard()
    try: s = mock_engine.add_orders(db, payload.session_id, payload.count)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("ADD_ORDERS", s.id)


@router.post("/increase-gmv")
async def increase_gmv(payload: MockMoneyRequest, db: Session = Depends(get_db)):
    _guard()
    try: s = mock_engine.increase_gmv(db, payload.session_id, payload.amount)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("INCREASE_GMV", s.id)


@router.post("/add-ads")
async def add_ads(payload: MockMoneyRequest, db: Session = Depends(get_db)):
    _guard()
    try: s = mock_engine.add_ads(db, payload.session_id, payload.amount)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("ADD_ADS", s.id)


@router.post("/cancel-order")
async def cancel_order(payload: MockSessionRequest, db: Session = Depends(get_db)):
    _guard()
    try: mock_engine.cancel_random_order(db, payload.session_id)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("CANCEL_ORDER", payload.session_id)


@router.post("/refund-order")
async def refund_order(payload: MockSessionRequest, db: Session = Depends(get_db)):
    _guard()
    try: mock_engine.refund_random_order(db, payload.session_id)
    except ValueError as e: raise HTTPException(400, str(e))
    return await _done("REFUND_ORDER", payload.session_id)


@router.post("/snapshot/{session_id}/{snapshot_type}")
async def snapshot(session_id: int, snapshot_type: str, db: Session = Depends(get_db)):
    _guard(); s = db.get(LiveSession, session_id)
    if not s: raise HTTPException(404, "Session not found")
    snap = build_refund_snapshot(db, s, snapshot_type.upper())
    return await _done(f"SNAPSHOT_{snap.snapshot_type}", session_id)
