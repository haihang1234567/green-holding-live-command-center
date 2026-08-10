from __future__ import annotations
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auto_monitor import monitor_state,sync_session
from ..config import get_settings
from ..database import get_db
from ..live_runtime import ads_client,get_live_signal,profile_for_channel,shop_client
from ..models import Channel
from ..security import require_admin
settings=get_settings(); router=APIRouter(prefix="/integrations",tags=["integrations"])
def _profile_status(channel):
    p=profile_for_channel(channel)
    return {"slot":p.slot,"channel_id":channel.id,"channel_name":channel.name,"name":p.name,"shop":{"app_key":bool(p.app_key),"app_secret":bool(p.app_secret),"access_token":bool(p.access_token),"refresh_token":bool(p.refresh_token),"shop_cipher":bool(p.shop_cipher),"shop_id":p.shop_id or None},"ads":{"app_id":bool(p.ads_app_id),"secret":bool(p.ads_secret),"access_token":bool(p.ads_access_token),"advertiser_id":p.advertiser_id or None},"live":{"status_endpoint":bool(p.live_status_url),"status_mode":p.live_status_mode,"status_auth_mode":p.live_status_auth_mode,"metrics_endpoint":bool(p.live_metrics_url),"metrics_auth_mode":p.live_metrics_auth_mode}}
@router.get("/status")
def status(db:Session=Depends(get_db),_=Depends(require_admin)):
    channels=db.scalars(select(Channel).order_by(Channel.id)).all(); return {"data_provider":settings.data_provider.upper(),"live_status_provider":settings.live_status_provider.upper(),"polling_interval_seconds":settings.polling_interval_seconds,"refund_check_interval_seconds":180,"shops":[_profile_status(x) for x in channels],"monitor":monitor_state}
@router.get("/monitor/status")
def monitor_status(db:Session=Depends(get_db),_=Depends(require_admin)):
    channels=db.scalars(select(Channel).order_by(Channel.id)).all(); return {"mode":f"{settings.data_provider.upper()} / {settings.live_status_provider.upper()}","polling_interval_seconds":settings.polling_interval_seconds,"last_cycle_at":monitor_state.get("last_cycle_at"),"last_cycle_duration_ms":monitor_state.get("last_cycle_duration_ms"),"channels":[{**_profile_status(ch),"runtime":monitor_state.get("channels",{}).get(str(ch.id),{})} for ch in channels]}
@router.post("/test/live/{channel_id}")
async def test_live(channel_id:int,db:Session=Depends(get_db),_=Depends(require_admin)):
    ch=db.get(Channel,channel_id)
    if not ch:raise HTTPException(404,"Không tìm thấy kênh")
    try:return {"ok":True,"result":await get_live_signal(ch)}
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
@router.post("/test/shop/{channel_id}")
async def test_shop(channel_id:int,db:Session=Depends(get_db),_=Depends(require_admin)):
    if settings.data_provider.upper()!="TIKTOK":raise HTTPException(409,"DATA_PROVIDER chưa đặt thành TIKTOK")
    ch=db.get(Channel,channel_id)
    if not ch:raise HTTPException(404,"Không tìm thấy kênh")
    try:
        client,_=shop_client(ch); return {"ok":True,"shops":await client.get_authorized_shops()}
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
@router.post("/test/ads/{channel_id}")
async def test_ads(channel_id:int,db:Session=Depends(get_db),_=Depends(require_admin)):
    if settings.data_provider.upper()!="TIKTOK":raise HTTPException(409,"DATA_PROVIDER chưa đặt thành TIKTOK")
    ch=db.get(Channel,channel_id)
    if not ch:raise HTTPException(404,"Không tìm thấy kênh")
    try:
        client,_=ads_client(ch); end=datetime.now(timezone.utc); return {"ok":True,"data":await client.get_metrics(ch,end-timedelta(hours=2),end)}
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
@router.post("/sync/{session_id}")
async def sync(session_id:int,_=Depends(require_admin)):
    try:return await sync_session(session_id)
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
