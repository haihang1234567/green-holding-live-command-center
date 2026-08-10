from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import require_admin
from app.core.security import hash_password
from app.models import Team,Channel,ChannelShiftAssignment,User,LiveSession,Order
from app.schemas import UserCreateRequest,UserActiveRequest,ChannelUpdateRequest,AssignmentUpdateRequest,ManualLiveStartRequest,MockChannelRequest
from app.services.kpi import session_metrics,get_refund_snapshot
from app.services import mock_engine

router=APIRouter(prefix="/admin",tags=["admin-analytics"],dependencies=[Depends(require_admin)])

def _session_scope(db,team_id=None,channel_id=None):
    q=db.query(LiveSession)
    if team_id:q=q.filter(LiveSession.team_id==team_id)
    if channel_id:q=q.filter(LiveSession.channel_id==channel_id)
    return q

@router.get("/orders")
def orders(team_id:int|None=None,channel_id:int|None=None,status:str|None=None,limit:int=500,db:Session=Depends(get_db)):
    ids=[s.id for s in _session_scope(db,team_id,channel_id).all()]
    if not ids:return []
    q=db.query(Order).filter(Order.live_session_id.in_(ids))
    if status:q=q.filter(Order.order_status==status.upper())
    rows=q.order_by(Order.created_at.desc()).limit(min(limit,1000)).all();ss={s.id:s for s in db.query(LiveSession).filter(LiveSession.id.in_(ids)).all()}
    return [{"order_id":o.order_id,"session_id":o.live_session_id,"session_code":ss[o.live_session_id].session_code,"team_name":ss[o.live_session_id].team.name,"channel_name":ss[o.live_session_id].channel.name,"created_at":o.created_at,"sku_id":o.sku_id,"product_name":o.product_name,"quantity":o.quantity,"amount":o.amount,"payment_amount":o.payment_amount,"status":o.order_status,"refund_amount":o.refund_amount,"cancelled_amount":o.cancelled_amount} for o in rows]

@router.get("/products")
def products(team_id:int|None=None,channel_id:int|None=None,db:Session=Depends(get_db)):
    ids=[s.id for s in _session_scope(db,team_id,channel_id).all()]
    if not ids:return []
    rows=(db.query(Order.sku_id,Order.product_id,Order.product_name,func.sum(Order.quantity).label("quantity"),func.sum(Order.payment_amount).label("revenue"),func.count(Order.id).label("orders")).filter(Order.live_session_id.in_(ids)).group_by(Order.sku_id,Order.product_id,Order.product_name).order_by(func.sum(Order.payment_amount).desc()).all())
    total=sum(int(r.revenue or 0) for r in rows)
    return [{"sku_id":r.sku_id,"product_id":r.product_id,"product_name":r.product_name or "Chưa có dữ liệu","quantity":int(r.quantity or 0),"orders":int(r.orders or 0),"revenue":int(r.revenue or 0),"revenue_share":round(int(r.revenue or 0)/total*100,2) if total else 0} for r in rows]

@router.get("/ads")
def ads(team_id:int|None=None,channel_id:int|None=None,db:Session=Depends(get_db)):
    ss=_session_scope(db,team_id,channel_id).order_by(LiveSession.started_at.desc()).limit(200).all()
    return [{"session_id":s.id,"session_code":s.session_code,"team_name":s.team.name,"channel_name":s.channel.name,"started_at":s.started_at,"spend":s.current_ads_spend,"attributed_revenue":s.attributed_ads_revenue,"ads_gmv_pct":round(s.current_ads_spend/s.current_gmv*100,2) if s.current_gmv else 0,"roas":round((s.attributed_ads_revenue or s.current_gmv)/s.current_ads_spend,2) if s.current_ads_spend else 0} for s in ss]

@router.get("/teams")
def teams(snapshot_type:str="T3H",db:Session=Depends(get_db)):
    out=[]
    for t in db.query(Team).order_by(Team.id).all():
        ss=db.query(LiveSession).filter_by(team_id=t.id).all();gmv=orders=ads=net=0
        for s in ss:
            m=session_metrics(s,get_refund_snapshot(db,s.id,snapshot_type));gmv+=m['gmv'];orders+=m['orders'];ads+=m['ads_spend'];net+=m['net_revenue']
        out.append({"id":t.id,"name":t.name,"target_gmv":t.target_gmv,"sessions":len(ss),"gmv":gmv,"orders":orders,"ads_spend":ads,"net_revenue":net})
    return out

@router.get("/channels")
def channels(db:Session=Depends(get_db)):
    out=[]
    for c in db.query(Channel).order_by(Channel.id).all():
        live=db.query(LiveSession).filter_by(channel_id=c.id,status="LIVE").first()
        out.append({"id":c.id,"name":c.name,"status":c.status,"external_channel_id":c.external_channel_id,"tiktok_shop_id":c.tiktok_shop_id,"advertiser_id":c.advertiser_id,"live_session_id":live.id if live else None,"live_team":live.team.name if live else None})
    return out

@router.patch("/channels/{channel_id}")
def update_channel(channel_id:int,payload:ChannelUpdateRequest,db:Session=Depends(get_db)):
    c=db.get(Channel,channel_id)
    if not c:raise HTTPException(404,"Channel not found")
    for k,v in payload.model_dump(exclude_unset=True).items():setattr(c,k,v)
    db.commit();return {"ok":True}

@router.get("/assignments")
def assignments(db:Session=Depends(get_db)):
    return [{"id":a.id,"channel_id":a.channel_id,"channel_name":a.channel.name,"team_id":a.team_id,"team_name":a.team.name,"shift":a.shift,"start_hour":a.start_hour,"end_hour":a.end_hour,"active":a.active} for a in db.query(ChannelShiftAssignment).order_by(ChannelShiftAssignment.id).all()]

@router.patch("/assignments/{assignment_id}")
def update_assignment(assignment_id:int,payload:AssignmentUpdateRequest,db:Session=Depends(get_db)):
    a=db.get(ChannelShiftAssignment,assignment_id)
    if not a:raise HTTPException(404,"Assignment not found")
    for k,v in payload.model_dump(exclude_unset=True).items():setattr(a,k,v)
    db.commit();return {"ok":True}

@router.get("/users")
def users(db:Session=Depends(get_db)):
    return [{"id":u.id,"username":u.username,"role":u.role,"team_id":u.team_id,"team_name":u.team.name if u.team else None,"active":u.active} for u in db.query(User).order_by(User.id).all()]

@router.post("/users")
def create_user(payload:UserCreateRequest,db:Session=Depends(get_db)):
    if db.query(User).filter_by(username=payload.username).first():raise HTTPException(409,"Username already exists")
    if payload.role.upper()=="TEAM" and not payload.team_id:raise HTTPException(400,"team_id is required for TEAM user")
    u=User(username=payload.username,password_hash=hash_password(payload.password),role=payload.role.upper(),team_id=payload.team_id,active=True);db.add(u);db.commit();db.refresh(u);return {"id":u.id,"username":u.username}

@router.patch("/users/{user_id}/active")
def set_user_active(user_id:int,payload:UserActiveRequest,db:Session=Depends(get_db)):
    u=db.get(User,user_id)
    if not u:raise HTTPException(404,"User not found")
    u.active=payload.active;db.commit();return {"ok":True}

@router.post("/manual-live/start")
def manual_start(payload:ManualLiveStartRequest,db:Session=Depends(get_db)):
    try:s=mock_engine.start_live(db,payload.channel_id,payload.team_id,payload.shift)
    except ValueError as e:raise HTTPException(400,str(e))
    return {"ok":True,"session_id":s.id}

@router.post("/manual-live/stop")
def manual_stop(payload:MockChannelRequest,db:Session=Depends(get_db)):
    try:s=mock_engine.stop_live(db,payload.channel_id)
    except ValueError as e:raise HTTPException(400,str(e))
    return {"ok":True,"session_id":s.id}
