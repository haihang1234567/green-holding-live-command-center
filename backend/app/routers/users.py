from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Team, User, UserRole
from ..security import hash_password, require_admin

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    role: str = UserRole.TEAM.value
    team_id: int | None = None


class UserUpdate(BaseModel):
    role: str | None = None
    team_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


def serialize(row: User) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "role": row.role,
        "team_id": row.team_id,
        "team_name": row.team.name if row.team else None,
        "is_active": row.is_active,
    }


@router.get("")
def list_users(db: Session = Depends(get_db), _=Depends(require_admin)):
    rows = db.scalars(select(User).options(joinedload(User.team)).order_by(User.id)).unique().all()
    return [serialize(x) for x in rows]


@router.post("")
def create_user(payload: UserCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    username = payload.username.strip().lower()
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(409, "Username đã tồn tại")
    role = payload.role.upper()
    if role not in {UserRole.ADMIN.value, UserRole.TEAM.value}:
        raise HTTPException(400, "Role không hợp lệ")
    if role == UserRole.TEAM.value:
        if not payload.team_id or not db.get(Team, payload.team_id):
            raise HTTPException(400, "TEAM user phải gắn với một team hợp lệ")
    row = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=role,
        team_id=payload.team_id if role == UserRole.TEAM.value else None,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if row.team_id:
        row = db.scalar(select(User).options(joinedload(User.team)).where(User.id == row.id)) or row
    return serialize(row)


@router.patch("/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    row = db.get(User, user_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy người dùng")
    if payload.role is not None:
        role = payload.role.upper()
        if role not in {UserRole.ADMIN.value, UserRole.TEAM.value}:
            raise HTTPException(400, "Role không hợp lệ")
        row.role = role
    if payload.team_id is not None:
        if not db.get(Team, payload.team_id):
            raise HTTPException(400, "Team không hợp lệ")
        row.team_id = payload.team_id
    if row.role == UserRole.ADMIN.value:
        row.team_id = None
    elif not row.team_id:
        raise HTTPException(400, "TEAM user phải gắn với một team")
    if payload.is_active is not None:
        if row.id == admin.id and payload.is_active is False:
            raise HTTPException(400, "Không thể tự khóa tài khoản đang đăng nhập")
        row.is_active = payload.is_active
    if payload.password:
        row.password_hash = hash_password(payload.password)
    db.commit()
    row = db.scalar(select(User).options(joinedload(User.team)).where(User.id == row.id)) or row
    return serialize(row)
