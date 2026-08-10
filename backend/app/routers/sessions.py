from __future__ import annotations
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import select
from sqlalchemy.orm import Session,joinedload
from ..database import get_db
from ..live_models import LiveCoreSnapshot
from ..models import LiveMetricSnapshot,LiveSession,RefundSnapshot,User,UserRole
from ..security import get_current_user
from ..services import serialize_session
router=APIRouter(prefix="/sessions",tags=["sessions"])
@router.get("")
def list_sessions(status:str|None=Query(default=None),team_id:int|None=Query(default=None),channel_id:int|None=Query(default=None),limit:int=Query(default=100,le=500),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    q=select(LiveSession).options(joinedload(LiveSession.channel),joinedload(LiveSession.team))
    if status:q=q.where(LiveSession.status==status.upper())
    if user.role==UserRole.TEAM.value:q=q.where(LiveSession.team_id==user.team_id)
    elif team_id:q=q.where(LiveSession.team_id==team_id)
    if channel_id:q=q.where(LiveSession.channel_id==channel_id)
    return [serialize_session(db,x) for x in db.scalars(q.order_by(LiveSession.started_at.desc()).limit(limit)).unique().all()]
@router.get("/{session_id}")
def get_session(session_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    s=db.scalar(select(LiveSession).options(joinedload(LiveSession.channel),joinedload(LiveSession.team)).where(LiveSession.id==session_id))
    if not s:raise HTTPException(404,"Không tìm thấy phiên LIVE")
    if user.role==UserRole.TEAM.value and user.team_id!=s.team_id:raise HTTPException(403,"Không có quyền xem phiên này")
    metrics=db.scalars(select(LiveMetricSnapshot).where(LiveMetricSnapshot.session_id==session_id).order_by(LiveMetricSnapshot.timestamp)).all(); core=db.scalars(select(LiveCoreSnapshot).where(LiveCoreSnapshot.session_id==session_id).order_by(LiveCoreSnapshot.captured_at)).all(); refunds=db.scalars(select(RefundSnapshot).where(RefundSnapshot.session_id==session_id).order_by(RefundSnapshot.hours_after_live)).all(); latest=core[-1] if core else None
    return {**serialize_session(db,s),"timeline":[{"timestamp":x.timestamp,"gmv":float(x.gmv or 0),"orders":x.orders,"ads_spend":float(x.ads_spend or 0),"current_viewers":x.current_viewers} for x in metrics],"live_core_latest":None if not latest else {"captured_at":latest.captured_at,"gmv":float(latest.gmv) if latest.gmv is not None else None,"orders":latest.orders,"paid_orders":latest.paid_orders,"buyers":latest.buyers,"current_viewers":latest.current_viewers,"peak_viewers":latest.peak_viewers,"product_views":latest.product_views,"ctr":latest.ctr,"comments":latest.comments,"shares":latest.shares,"avg_watch_seconds":latest.avg_watch_seconds},"refund_snapshots":[{"id":x.id,"snapshot_type":x.snapshot_type,"hours_after_live":x.hours_after_live,"snapshot_time":x.snapshot_time,"original_gmv":float(x.original_gmv or 0),"refund_amount":float(x.refund_amount or 0),"cancelled_amount":float(x.cancelled_amount or 0),"refund_cancel_rate":x.refund_cancel_rate,"net_revenue":float(x.net_revenue or 0),"total_orders":x.total_orders,"cancelled_orders":x.cancelled_orders} for x in refunds]}
