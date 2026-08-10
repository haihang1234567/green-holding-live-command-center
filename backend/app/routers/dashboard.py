from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..security import get_current_user
from ..services import dashboard_overview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    team_id = user.team_id if user.role == UserRole.TEAM.value else None
    return dashboard_overview(db, team_id=team_id)
