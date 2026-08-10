from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..attribution import session_attribution_summary
from ..database import get_db
from ..models import AdsSnapshot, LiveSession, Order, Product, User, UserRole
from ..security import get_current_user

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/orders")
def orders(
    session_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Order)
    if session_id:
        # In production this now means EXACT LIVE-attributed orders only.
        query = query.where(Order.live_session_id == session_id)
    if user.role == UserRole.TEAM.value:
        query = query.join(LiveSession, Order.live_session_id == LiveSession.id).where(LiveSession.team_id == user.team_id)
    rows = db.scalars(query.order_by(Order.created_at.desc()).limit(limit)).all()
    return [{
        "id": x.id, "order_id": x.parent_order_id or x.order_id, "session_id": x.live_session_id,
        "created_at": x.created_at, "sku_id": x.sku_id, "product_id": x.product_id, "product_name": x.product_name,
        "quantity": x.quantity, "amount": float(x.payment_amount or 0), "status": x.order_status,
        "refund_amount": float(x.refund_amount or 0), "cancelled_amount": float(x.cancelled_amount or 0),
    } for x in rows]


@router.get("/attribution/{session_id}")
def attribution(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "Không tìm thấy phiên LIVE")
    if user.role == UserRole.TEAM.value and user.team_id != session.team_id:
        raise HTTPException(403, "Không có quyền xem phiên này")
    return session_attribution_summary(db, session_id)


@router.get("/products")
def products(limit: int = Query(default=200, le=1000), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Product)
    if user.role == UserRole.TEAM.value:
        query = query.join(Order, (Order.sku_id == Product.sku_id) & (Order.channel_id == Product.channel_id)).join(LiveSession, Order.live_session_id == LiveSession.id).where(LiveSession.team_id == user.team_id).distinct()
    rows = db.scalars(query.order_by(Product.updated_at.desc()).limit(limit)).all()
    return [{"id": x.id, "product_id": x.product_id, "sku_id": x.sku_id, "name": x.product_name, "price": float(x.price or 0), "currency": x.currency, "channel_id": x.channel_id} for x in rows]


@router.get("/ads")
def ads(session_id: int | None = None, limit: int = Query(default=200, le=1000), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(AdsSnapshot)
    if session_id:
        query = query.where(AdsSnapshot.live_session_id == session_id)
    if user.role == UserRole.TEAM.value:
        query = query.join(LiveSession, AdsSnapshot.live_session_id == LiveSession.id).where(LiveSession.team_id == user.team_id)
    rows = db.scalars(query.order_by(AdsSnapshot.timestamp.desc()).limit(limit)).all()
    return [{"id": x.id, "session_id": x.live_session_id, "timestamp": x.timestamp, "spend": float(x.spend or 0), "impressions": x.impressions, "clicks": x.clicks, "orders": x.orders, "gross_revenue": float(x.gross_revenue or 0), "roas": x.roas} for x in rows]
