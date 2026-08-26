from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import get_settings
from ..models import Alert, AppSetting, Channel, Team
from ..schedule import DailyTeamAssignment, day_schedule, vietnam_date
from ..security import get_current_user, require_admin

router = APIRouter(tags=["admin"])
settings = get_settings()


class ChannelUpdate(BaseModel):
    name: str | None = None
    handle: str | None = None
    tiktok_shop_id: str | None = None
    shop_cipher: str | None = None
    advertiser_id: str | None = None
    live_source_key: str | None = None
    polling_enabled: bool | None = None


class DailyScheduleUpdate(BaseModel):
    channel_1_ca_sang_team_id: int | None = None
    channel_1_ca_toi_team_id: int | None = None
    channel_2_ca_sang_team_id: int | None = None
    channel_2_ca_toi_team_id: int | None = None


class ThresholdUpdate(BaseModel):
    refund_warning_percent: float | None = None
    ads_gmv_warning_percent: float | None = None
    gmv_velocity_drop_percent: float | None = None


SCHEDULE_FIELDS = {
    "channel_1_ca_sang_team_id": (1, "CA_SANG"),
    "channel_1_ca_toi_team_id": (1, "CA_TOI"),
    "channel_2_ca_sang_team_id": (2, "CA_SANG"),
    "channel_2_ca_toi_team_id": (2, "CA_TOI"),
}


@router.get("/channels")
def channels(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.scalars(select(Channel).where(Channel.id.in_(settings.active_channel_ids)).order_by(Channel.id)).all()
    is_admin = user.role == "ADMIN"
    return [{
        "id": x.id, "name": x.name, "handle": x.handle, "status": x.status,
        "tiktok_shop_id": x.tiktok_shop_id if is_admin else None,
        "shop_cipher": x.shop_cipher if is_admin else None,
        "advertiser_id": x.advertiser_id if is_admin else None,
        "live_source_key": x.live_source_key if is_admin else None,
        "polling_enabled": x.polling_enabled if is_admin else None,
    } for x in rows]


@router.patch("/channels/{channel_id}")
def update_channel(channel_id: int, payload: ChannelUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if channel_id not in settings.active_channel_ids:
        raise HTTPException(404, "Shop này chưa được kích hoạt")
    row = db.get(Channel, channel_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy kênh")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    return {"ok": True}


@router.get("/teams")
def teams(db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = select(Team).order_by(Team.id)
    if user.role == "TEAM":
        query = query.where(Team.id == user.team_id)
    return [{"id": x.id, "name": x.name, "target_gmv": float(x.target_gmv or 0)} for x in db.scalars(query).all()]


@router.get("/alerts")
def alerts(db: Session = Depends(get_db), user=Depends(get_current_user)):
    query = select(Alert).where(Alert.channel_id.in_(settings.active_channel_ids) | Alert.channel_id.is_(None)).order_by(Alert.created_at.desc()).limit(200)
    if user.role == "TEAM":
        from ..models import LiveSession
        query = query.join(LiveSession, Alert.session_id == LiveSession.id).where(LiveSession.team_id == user.team_id)
    rows = db.scalars(query).all()
    return [{"id": x.id, "type": x.alert_type, "severity": x.severity, "title": x.title, "message": x.message, "created_at": x.created_at, "acknowledged": x.acknowledged} for x in rows]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    row = db.get(Alert, alert_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy cảnh báo")
    row.acknowledged = True
    db.commit()
    return {"ok": True}


@router.get("/settings/thresholds")
def thresholds(db: Session = Depends(get_db), _=Depends(get_current_user)):
    keys = ["refund_warning_percent", "ads_gmv_warning_percent", "gmv_velocity_drop_percent"]
    values = {x.key: x.value for x in db.scalars(select(AppSetting).where(AppSetting.key.in_(keys))).all()}
    defaults = {"refund_warning_percent": "20", "ads_gmv_warning_percent": "8", "gmv_velocity_drop_percent": "30"}
    return {key: float(values.get(key, defaults[key])) for key in keys}


@router.patch("/settings/thresholds")
def update_thresholds(payload: ThresholdUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    for key, value in payload.model_dump(exclude_none=True).items():
        row = db.get(AppSetting, key)
        if row:
            row.value = str(value)
        else:
            db.add(AppSetting(key=key, value=str(value)))
    db.commit()
    return {"ok": True}


@router.get("/settings/daily-schedule/{work_date}")
def get_daily_schedule(work_date: date, db: Session = Depends(get_db), _=Depends(get_current_user)):
    assignments = day_schedule(db, work_date)
    active_fields = [field for field, (channel_id, _) in SCHEDULE_FIELDS.items() if channel_id in settings.active_channel_ids]
    return {
        "date": work_date.isoformat(),
        "is_today_vietnam": work_date == vietnam_date(),
        "active_shop_count": len(settings.active_channel_ids),
        "complete": all(assignments[field] is not None for field in active_fields),
        **assignments,
    }


@router.put("/settings/daily-schedule/{work_date}")
def save_daily_schedule(work_date: date, payload: DailyScheduleUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    supplied = payload.model_dump(exclude_unset=True)
    for field, team_id in supplied.items():
        channel_id, shift = SCHEDULE_FIELDS[field]
        if channel_id not in settings.active_channel_ids:
            continue
        existing = db.scalar(
            select(DailyTeamAssignment).where(
                DailyTeamAssignment.work_date == work_date,
                DailyTeamAssignment.channel_id == channel_id,
                DailyTeamAssignment.shift == shift,
            )
        )
        if team_id in (None, 0):
            if existing:
                db.delete(existing)
            continue
        if not db.get(Team, team_id):
            raise HTTPException(400, f"Team {team_id} không hợp lệ")
        if existing:
            existing.team_id = team_id
        else:
            db.add(DailyTeamAssignment(work_date=work_date, channel_id=channel_id, shift=shift, team_id=team_id))
    db.commit()
    assignments = day_schedule(db, work_date)
    active_fields = [field for field, (channel_id, _) in SCHEDULE_FIELDS.items() if channel_id in settings.active_channel_ids]
    return {
        "ok": True,
        "date": work_date.isoformat(),
        "active_shop_count": len(settings.active_channel_ids),
        "complete": all(assignments[field] is not None for field in active_fields),
        **assignments,
    }
