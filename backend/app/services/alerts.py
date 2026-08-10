from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models import Alert, LiveSession, RefundSnapshot, LiveMetricSnapshot, AppSetting

def _aware(dt): return dt if (dt and dt.tzinfo) else (dt.replace(tzinfo=timezone.utc) if dt else None)
def threshold(db: Session, key: str, default: float) -> float:
    row=db.query(AppSetting).filter(AppSetting.key==key).first()
    try: return float(row.value) if row else default
    except (TypeError,ValueError): return default

def create_alert(db:Session,alert_type:str,title:str,message:str,session_id:int|None=None,severity:str="WARNING"):
    a=Alert(live_session_id=session_id,alert_type=alert_type,severity=severity,title=title,message=message);db.add(a);db.commit();db.refresh(a);return a

def _recent_duplicate(db,session_id,alert_type,minutes=30):
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=minutes)
    rows=db.query(Alert).filter(Alert.live_session_id==session_id,Alert.alert_type==alert_type).order_by(Alert.created_at.desc()).limit(20).all()
    return next((a for a in rows if _aware(a.created_at) and _aware(a.created_at)>=cutoff),None)

def evaluate_session_alerts(db:Session,session:LiveSession):
    gmv=int(session.current_gmv or 0);ads=int(session.current_ads_spend or 0);ads_limit=threshold(db,"ads_gmv_threshold_pct",8.0);ads_pct=ads/gmv*100 if gmv else 0
    if gmv and ads_pct>ads_limit and not _recent_duplicate(db,session.id,"ADS_WARNING"): create_alert(db,"ADS_WARNING","Ads/GMV vượt ngưỡng",f"Ads/GMV hiện tại {ads_pct:.2f}% > {ads_limit:.2f}%",session.id)
    now=datetime.now(timezone.utc); snaps=db.query(LiveMetricSnapshot).filter(LiveMetricSnapshot.session_id==session.id).order_by(LiveMetricSnapshot.timestamp.asc()).all(); recent=[x for x in snaps if _aware(x.timestamp)>=now-timedelta(minutes=35)]
    if len(recent)>=3:
        nearest=lambda target:min(recent,key=lambda s:abs((_aware(s.timestamp)-target).total_seconds()))
        s30=nearest(now-timedelta(minutes=30));s15=nearest(now-timedelta(minutes=15));prev=max(int(s15.gmv or 0)-int(s30.gmv or 0),0);cur=max(gmv-int(s15.gmv or 0),0);limit=threshold(db,"gmv_velocity_drop_pct",30.0)
        if prev>0:
            drop=(1-cur/prev)*100
            if drop>limit and not _recent_duplicate(db,session.id,"GMV_VELOCITY_WARNING"): create_alert(db,"GMV_VELOCITY_WARNING","GMV giảm tốc",f"15 phút gần nhất thấp hơn {drop:.1f}% so với 15 phút trước.",session.id)

def evaluate_refund_alert(db:Session,snapshot:RefundSnapshot):
    limit=threshold(db,"refund_threshold_pct",20.0)
    if snapshot.refund_cancel_rate>limit:
        old=db.query(Alert).filter(Alert.live_session_id==snapshot.session_id,Alert.alert_type=="REFUND_WARNING",Alert.message.contains(snapshot.snapshot_type)).first()
        if not old:create_alert(db,"REFUND_WARNING","Tỷ lệ hoàn/hủy cao",f"{snapshot.snapshot_type}: {snapshot.refund_cancel_rate:.2f}% > {limit:.2f}%",snapshot.session_id,"CRITICAL")
