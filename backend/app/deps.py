from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.core.security import decode_access_token


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    token = _token_from_header(authorization)
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid access token")
    user = db.query(User).filter(User.username == payload.get("sub"), User.active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def require_team_or_admin(user: User = Depends(get_current_user)) -> User:
    return user
