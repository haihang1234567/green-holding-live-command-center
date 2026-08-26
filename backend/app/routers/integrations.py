from __future__ import annotations
import html
import hmac
import logging
from datetime import datetime,timedelta,timezone
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auto_monitor import monitor_state,sync_session
from ..config import Settings,get_settings
from ..database import SessionLocal,get_db
from ..live_runtime import ads_client,get_live_signal,profile_for_channel,shop_client
from ..models import Channel
from ..providers import TikTokShopProvider
from ..security import require_admin
from ..tiktok_credentials import delete_pending_authorization,has_shop_authorization,store_pending_authorization,store_shop_authorization
settings=get_settings(); router=APIRouter(prefix="/integrations",tags=["integrations"])
logger=logging.getLogger(__name__)
def _profile_status(channel):
    p=profile_for_channel(channel)
    stored=has_shop_authorization(p.shop_cipher) if p.shop_cipher else False
    return {"slot":p.slot,"channel_id":channel.id,"channel_name":channel.name,"name":p.name,"shop":{"app_key":bool(p.app_key),"app_secret":bool(p.app_secret),"access_token":bool(p.access_token) or stored,"refresh_token":bool(p.refresh_token) or stored,"shop_cipher":bool(p.shop_cipher),"shop_id":p.shop_id or None},"ads":{"app_id":bool(p.ads_app_id),"secret":bool(p.ads_secret),"access_token":bool(p.ads_access_token),"advertiser_id":p.advertiser_id or None},"live":{"status_endpoint":bool(p.live_status_url),"status_mode":p.live_status_mode,"status_auth_mode":p.live_status_auth_mode,"metrics_endpoint":bool(p.live_metrics_url),"metrics_auth_mode":p.live_metrics_auth_mode}}

def _oauth_credentials()->tuple[str,str,str]:
    app_key=settings.tiktok_shop_app_key or settings.shop1_app_key
    app_secret=settings.tiktok_shop_app_secret or settings.shop1_app_secret
    auth_url=settings.tiktok_shop_auth_url or settings.shop1_auth_url
    return app_key,app_secret,auth_url.rstrip("/")

def _shop_value(shop:dict,*keys:str)->str:
    for key in keys:
        value=shop.get(key)
        if value not in (None,""):return str(value)
    return ""

def _page(title:str,message:str,*,ok:bool,status_code:int=200)->HTMLResponse:
    color="#087f5b" if ok else "#c92a2a"
    safe_title=html.escape(title);safe_message=html.escape(message)
    body=f"""<!doctype html><html lang=\"vi\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{safe_title}</title><style>body{{margin:0;background:#f4f7f6;color:#17211f;font-family:Inter,system-ui,sans-serif}}main{{max-width:680px;margin:10vh auto;padding:36px;background:white;border-radius:18px;box-shadow:0 18px 55px #163c2c1f}}h1{{color:{color};margin-top:0}}p{{font-size:17px;line-height:1.6}}a{{display:inline-block;margin-top:12px;color:white;background:#087f5b;padding:12px 18px;border-radius:10px;text-decoration:none}}</style></head><body><main><h1>{safe_title}</h1><p>{safe_message}</p><a href=\"/\">Quay lại Command Center</a></main></body></html>"""
    return HTMLResponse(body,status_code=status_code,headers={"Cache-Control":"no-store"})

@router.get("/tiktok/callback",response_class=HTMLResponse)
async def tiktok_callback(request:Request):
    query=request.query_params
    error=query.get("error") or query.get("error_code")
    if error:
        return _page("Ủy quyền TikTok không thành công",query.get("error_description") or str(error),ok=False,status_code=400)
    code=query.get("code") or query.get("auth_code") or ""
    state=query.get("state") or ""
    if not code:
        return _page("Thiếu mã ủy quyền","TikTok không gửi code/auth_code về callback.",ok=False,status_code=400)
    if settings.tiktok_oauth_state:
        allowed_states={settings.tiktok_oauth_state,f"{settings.tiktok_oauth_state}:shop1",f"{settings.tiktok_oauth_state}:shop2"}
        if not any(hmac.compare_digest(state,allowed) for allowed in allowed_states):
            return _page("State không hợp lệ","Yêu cầu ủy quyền không khớp cấu hình bảo mật.",ok=False,status_code=400)
    app_key,app_secret,auth_url=_oauth_credentials()
    if not app_key or not app_secret:
        return _page("Ứng dụng chưa có credentials","Hãy cấu hình App Key và App Secret trong Render Environment trước.",ok=False,status_code=503)
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.get(f"{auth_url}/token/get",params={"app_key":app_key,"app_secret":app_secret,"auth_code":code,"grant_type":"authorized_code"})
            response.raise_for_status();payload=response.json()
        data=payload.get("data") or {}
        if payload.get("code") not in (0,None) or not data.get("access_token"):
            raise RuntimeError(str(payload.get("message") or "TikTok không trả access token"))
        access_token=str(data["access_token"]);refresh_token=str(data.get("refresh_token") or "")
        pending_key=store_pending_authorization(access_token,access_token=access_token,refresh_token=refresh_token,metadata={k:v for k,v in data.items() if k not in {"access_token","refresh_token"}})
        api_settings=Settings(tiktok_shop_base_url=settings.tiktok_shop_base_url,tiktok_shop_auth_url=auth_url,tiktok_shop_app_key=app_key,tiktok_shop_app_secret=app_secret,tiktok_shop_access_token=access_token,tiktok_shop_refresh_token=refresh_token)
        shops=await TikTokShopProvider(api_settings).get_authorized_shops()
        if not shops:
            return _page("Đã nhận token","Token đã được lưu mã hóa nhưng TikTok chưa trả thông tin shop. Hãy kiểm tra quyền Shop Authorized Information.",ok=False,status_code=502)
        for shop in shops:
            cipher=_shop_value(shop,"cipher","shop_cipher")
            if not cipher:continue
            store_shop_authorization(cipher,access_token=access_token,refresh_token=refresh_token,metadata={"shop_id":_shop_value(shop,"id","shop_id"),"shop_name":_shop_value(shop,"name","shop_name"),"region":_shop_value(shop,"region","shop_region"),"token_expires_in":data.get("access_token_expire_in") or data.get("access_token_expire_time")})
        selected=shops[0]
        selected_cipher=_shop_value(selected,"cipher","shop_cipher")
        selected_id=_shop_value(selected,"id","shop_id")
        state_slot=state.rsplit(":",1)[-1].lower()
        slot=1 if state_slot in {"1","shop1","shop_1"} else 2 if state_slot in {"2","shop2","shop_2"} else 0
        if slot and selected_cipher:
            channel_id=settings.shop1_channel_id if slot==1 else settings.shop2_channel_id
            with SessionLocal() as db:
                channel=db.get(Channel,channel_id)
                if channel:
                    channel.shop_cipher=selected_cipher
                    if selected_id:channel.tiktok_shop_id=selected_id
                    db.commit()
        delete_pending_authorization(pending_key)
        names=", ".join(_shop_value(shop,"name","shop_name","id","shop_id") or "TikTok Shop" for shop in shops)
        return _page("Đã kết nối TikTok Shop",f"Đã lưu token mã hóa cho: {names}. Bạn có thể quay lại Command Center.",ok=True)
    except httpx.HTTPError:
        logger.exception("TikTok OAuth token request failed")
        return _page("Không kết nối được TikTok","TikTok token API không phản hồi thành công. Hãy thử lại bằng authorization link mới.",ok=False,status_code=502)
    except Exception:
        logger.exception("TikTok OAuth callback failed")
        return _page("Không hoàn tất ủy quyền","Backend không thể hoàn tất kết nối shop. Hãy kiểm tra quyền API và thử lại bằng authorization link mới.",ok=False,status_code=502)
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
        client,p=shop_client(ch); return {"ok":True,"shops":await client.get_authorized_shops(p.shop_cipher)}
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
