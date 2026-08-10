from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import require_team_or_admin
from app.models import LiveSession, User
from app.services.kpi import session_metrics, get_refund_snapshot, top_skus

router = APIRouter(prefix="/team", tags=["team"])


@router.get("/dashboard")
def dashboard(snapshot_type: str = "T3H", db: Session = Depends(get_db), user: User = Depends(require_team_or_admin)):
    if user.role == "ADMIN" and not user.team_id:
        raise HTTPException(400, "Admin must use admin dashboard")
    team_id = user.team_id
    sessions = db.query(LiveSession).filter(LiveSession.team_id == team_id).order_by(LiveSession.started_at.desc()).all()
    current = next((s for s in sessions if s.status == "LIVE"), None)
    latest = current or (sessions[0] if sessions else None)
    if not latest:
        return {"team": {"id": user.team.id, "name": user.team.name, "target_gmv": user.team.target_gmv}, "session": None, "history": []}
    snap = get_refund_snapshot(db, latest.id, snapshot_type)
    m = session_metrics(latest, snap)
    return {"team": {"id": user.team.id, "name": user.team.name, "target_gmv": user.team.target_gmv}, "session": {"id": latest.id, "session_code": latest.session_code, "channel_name": latest.channel.name, "shift": latest.shift, "status": latest.status, "started_at": latest.started_at, "ended_at": latest.ended_at, "metrics": m, "top_skus": top_skus(db, latest.id)}, "progress_pct": round(m["gmv"] / user.team.target_gmv * 100, 1) if user.team.target_gmv else 0, "history": [{"id": s.id, "session_code": s.session_code, "started_at": s.started_at, "status": s.status, "gmv": s.current_gmv} for s in sessions[:10]]}
