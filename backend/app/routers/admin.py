from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import require_admin
from app.models import Alert, Channel, ChannelShiftAssignment, LiveSession, RefundSnapshot, Team, LiveMetricSnapshot
from app.services.kpi import session_metrics, get_refund_snapshot, top_skus, SNAPSHOT_ORDER

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def serialize_session(db: Session, s: LiveSession, snapshot_type: str = "T3H"):
    snap = get_refund_snapshot(db, s.id, snapshot_type)
    return {
        "id": s.id, "session_code": s.session_code,
        "channel_id": s.channel_id, "channel_name": s.channel.name,
        "team_id": s.team_id, "team_name": s.team.name,
        "shift": s.shift, "started_at": s.started_at, "ended_at": s.ended_at,
        "status": s.status, "metrics": session_metrics(s, snap),
    }


def _ranking(db: Session, snapshot_type: str):
    rows = []
    for team in db.query(Team).order_by(Team.id).all():
        sessions = db.query(LiveSession).filter(LiveSession.team_id == team.id).all()
        if not sessions:
            continue
        gmv = orders = ads = net = refund_loss = 0
        hours = 0.0
        for s in sessions:
            m = session_metrics(s, get_refund_snapshot(db, s.id, snapshot_type))
            gmv += m["gmv"]; orders += m["orders"]; ads += m["ads_spend"]; net += m["net_revenue"]
            refund_loss += max(m["gmv"] - m["net_revenue"], 0)
            hours += max(m["duration_seconds"] / 3600, 1 / 60)
        rows.append({
            "team_id": team.id, "team_name": team.name, "gmv": gmv, "orders": orders,
            "aov": round(gmv / orders) if orders else 0, "ads_spend": ads,
            "ads_gmv_pct": round(ads / gmv * 100, 2) if gmv else 0,
            "roas": round(gmv / ads, 2) if ads else 0,
            "refund_rate": round(refund_loss / gmv * 100, 2) if gmv else 0,
            "net_revenue": net, "gmv_per_hour": round(gmv / hours) if hours else 0,
        })
    rows.sort(key=lambda x: x["net_revenue"], reverse=True)
    for i, row in enumerate(rows, 1): row["rank"] = i
    return rows


@router.get("/overview")
def overview(snapshot_type: str = Query("T3H"), db: Session = Depends(get_db)):
    if snapshot_type not in SNAPSHOT_ORDER: snapshot_type = "T3H"
    today = datetime.now(timezone.utc).date()
    sessions = db.query(LiveSession).all()
    live = [s for s in sessions if s.status == "LIVE"]
    today_sessions = [s for s in sessions if s.started_at.date() == today]
    base_sessions = today_sessions if today_sessions else sessions[:4]
    totals = {"gmv": 0, "orders": 0, "ads_spend": 0, "net_revenue": 0}
    refund_loss = 0
    for s in base_sessions:
        m = session_metrics(s, get_refund_snapshot(db, s.id, snapshot_type))
        for key in ["gmv", "orders", "ads_spend", "net_revenue"]: totals[key] += m[key]
        refund_loss += max(m["gmv"] - m["net_revenue"], 0)
    totals["aov"] = round(totals["gmv"] / totals["orders"]) if totals["orders"] else 0
    totals["ads_gmv_pct"] = round(totals["ads_spend"] / totals["gmv"] * 100, 2) if totals["gmv"] else 0
    totals["refund_rate"] = round(refund_loss / totals["gmv"] * 100, 2) if totals["gmv"] else 0
    totals["roas"] = round(totals["gmv"] / totals["ads_spend"], 2) if totals["ads_spend"] else 0
    channels = []
    for c in db.query(Channel).order_by(Channel.id).all():
        current = db.query(LiveSession).filter(LiveSession.channel_id == c.id, LiveSession.status == "LIVE").order_by(LiveSession.started_at.desc()).first()
        channels.append({"id": c.id, "name": c.name, "status": c.status, "session": serialize_session(db, current, snapshot_type) if current else None})
    alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(6).all()
    return {"snapshot_type": snapshot_type, "totals": totals, "channels": channels, "live_count": len(live),
            "alerts": [{"id": a.id, "title": a.title, "message": a.message, "severity": a.severity, "created_at": a.created_at, "acknowledged": a.acknowledged} for a in alerts],
            "ranking": _ranking(db, snapshot_type)}


@router.get("/ranking")
def ranking(snapshot_type: str = "T3H", db: Session = Depends(get_db)):
    return _ranking(db, snapshot_type if snapshot_type in SNAPSHOT_ORDER else "T3H")


@router.get("/sessions")
def sessions(status: str | None = None, team_id: int | None = None, channel_id: int | None = None, snapshot_type: str = "T3H", db: Session = Depends(get_db)):
    q = db.query(LiveSession)
    if status: q = q.filter(LiveSession.status == status.upper())
    if team_id: q = q.filter(LiveSession.team_id == team_id)
    if channel_id: q = q.filter(LiveSession.channel_id == channel_id)
    return [serialize_session(db, s, snapshot_type) for s in q.order_by(LiveSession.started_at.desc()).limit(200).all()]


@router.get("/sessions/{session_id}")
def session_detail(session_id: int, snapshot_type: str = "T3H", db: Session = Depends(get_db)):
    s = db.get(LiveSession, session_id)
    if not s: raise HTTPException(404, "Session not found")
    metrics = db.query(LiveMetricSnapshot).filter(LiveMetricSnapshot.session_id == s.id).order_by(LiveMetricSnapshot.timestamp).all()
    refunds = db.query(RefundSnapshot).filter(RefundSnapshot.session_id == s.id).order_by(RefundSnapshot.id).all()
    data = serialize_session(db, s, snapshot_type)
    data["top_skus"] = top_skus(db, s.id, 8)
    data["timeline"] = [{"timestamp": m.timestamp, "gmv": m.gmv, "orders": m.orders, "ads_spend": m.ads_spend} for m in metrics]
    data["refund_timeline"] = [{"snapshot_type": r.snapshot_type, "rate": r.refund_cancel_rate, "net_revenue": r.net_revenue, "refund_amount": r.refund_amount, "cancelled_amount": r.cancelled_amount} for r in refunds]
    return data


@router.get("/refunds/{session_id}")
def refund_timeline(session_id: int, db: Session = Depends(get_db)):
    rows = db.query(RefundSnapshot).filter(RefundSnapshot.session_id == session_id).all()
    by_type = {r.snapshot_type: r for r in rows}
    return [{"snapshot_type": s, "rate": by_type[s].refund_cancel_rate if s in by_type else None, "net_revenue": by_type[s].net_revenue if s in by_type else None} for s in SNAPSHOT_ORDER]


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    rows = db.query(Alert).order_by(Alert.created_at.desc()).limit(200).all()
    return [{"id": a.id, "session_id": a.live_session_id, "type": a.alert_type, "severity": a.severity, "title": a.title, "message": a.message, "created_at": a.created_at, "acknowledged": a.acknowledged} for a in rows]


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a: raise HTTPException(404, "Alert not found")
    a.acknowledged = True; db.commit(); return {"ok": True}


@router.get("/directory")
def directory(db: Session = Depends(get_db)):
    return {
        "teams": [{"id": t.id, "name": t.name, "target_gmv": t.target_gmv} for t in db.query(Team).order_by(Team.id).all()],
        "channels": [{"id": c.id, "name": c.name, "status": c.status, "external_channel_id": c.external_channel_id, "tiktok_shop_id": c.tiktok_shop_id, "advertiser_id": c.advertiser_id} for c in db.query(Channel).order_by(Channel.id).all()],
        "assignments": [{"id": a.id, "channel_id": a.channel_id, "team_id": a.team_id, "shift": a.shift, "start_hour": a.start_hour, "end_hour": a.end_hour, "active": a.active} for a in db.query(ChannelShiftAssignment).order_by(ChannelShiftAssignment.id).all()],
    }


@router.get("/settings")
def settings(db: Session = Depends(get_db)):
    from app.models import AppSetting
    return {r.key: r.value for r in db.query(AppSetting).order_by(AppSetting.key).all()}


@router.put("/settings/{key}")
def update_setting(key: str, payload: dict, db: Session = Depends(get_db)):
    from app.models import AppSetting
    if key not in {"refund_threshold_pct", "ads_gmv_threshold_pct", "gmv_velocity_drop_pct"}: raise HTTPException(400, "Unsupported setting")
    value = payload.get("value")
    try: float(value)
    except (TypeError, ValueError): raise HTTPException(400, "Setting value must be numeric")
    row = db.query(AppSetting).filter_by(key=key).first()
    if not row: row = AppSetting(key=key, value=str(value)); db.add(row)
    else: row.value = str(value)
    db.commit(); return {"key": key, "value": row.value}
