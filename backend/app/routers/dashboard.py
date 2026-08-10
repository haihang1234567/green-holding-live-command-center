from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..attribution import override_serialized_session
from ..database import get_db
from ..models import User, UserRole
from ..security import get_current_user
from ..services import dashboard_overview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    team_id = user.team_id if user.role == UserRole.TEAM.value else None
    payload = dashboard_overview(db, team_id=team_id)

    sessions = [override_serialized_session(db, dict(item)) for item in payload.get("sessions", [])]
    payload["sessions"] = sessions
    for channel in payload.get("channels", []):
        if channel.get("session"):
            channel["session"] = override_serialized_session(db, dict(channel["session"]))

    gmv = sum(float(x.get("gmv") or 0) for x in sessions)
    orders = sum(int(x.get("orders") or 0) for x in sessions)
    ads = sum(float(x.get("ads_spend") or 0) for x in sessions)
    refunds = sum(float(x.get("refund_amount") or 0) for x in sessions)
    cancelled = sum(float(x.get("cancelled_amount") or 0) for x in sessions)
    duration_hours = sum(max(float(x.get("duration_seconds") or 0) / 3600, 0) for x in sessions)
    payload["kpis"] = {
        "gmv": gmv,
        "orders": orders,
        "ads_spend": ads,
        "aov": gmv / orders if orders else 0,
        "ads_percentage": ads / gmv * 100 if gmv else 0,
        "roas": gmv / ads if ads else 0,
        "net_revenue": max(0, gmv - refunds - cancelled),
        "refund_rate": (refunds + cancelled) / gmv * 100 if gmv else 0,
        "gmv_per_hour": gmv / duration_hours if duration_hours else 0,
    }

    teams: dict[int, dict] = {}
    for item in sessions:
        row = teams.setdefault(item["team_id"], {"team_id": item["team_id"], "team_name": item["team_name"], "gmv": 0.0, "orders": 0, "ads": 0.0, "net": 0.0, "duration": 0})
        row["gmv"] += float(item.get("gmv") or 0)
        row["orders"] += int(item.get("orders") or 0)
        row["ads"] += float(item.get("ads_spend") or 0)
        row["net"] += float(item.get("net_revenue") or 0)
        row["duration"] += int(item.get("duration_seconds") or 0)
    ranking = []
    for row in teams.values():
        row["aov"] = row["gmv"] / row["orders"] if row["orders"] else 0
        row["ads_percentage"] = row["ads"] / row["gmv"] * 100 if row["gmv"] else 0
        row["gmv_per_hour"] = row["gmv"] / max(row["duration"] / 3600, 1 / 60)
        row["refund_rate"] = (row["gmv"] - row["net"]) / row["gmv"] * 100 if row["gmv"] else 0
        ranking.append(row)
    payload["ranking"] = sorted(ranking, key=lambda x: x["gmv"], reverse=True)
    payload["attribution_policy"] = "LIVE KPI = TikTok LIVE Analytics; order-level LIVE requires explicit content_type/content_id attribution."
    return payload
