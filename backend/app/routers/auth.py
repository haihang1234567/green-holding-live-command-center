from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username, User.is_active.is_(True)))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "role": user.role, "team_id": user.team_id, "team_name": user.team.name if user.team else None},
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role, "team_id": user.team_id, "team_name": user.team.name if user.team else None}
