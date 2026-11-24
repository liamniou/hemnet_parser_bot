from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

COOKIE = "hw_session"


def _serializer() -> URLSafeTimedSerializer:
    key = get_settings().secret_key
    if len(key) < 16:
        raise RuntimeError("SECRET_KEY is missing or too short")
    return URLSafeTimedSerializer(key, salt="session")


def set_session(response: Response, user: User) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE,
        _serializer().dumps({"uid": user.id, "tg": user.telegram_id}),
        max_age=s.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=s.public_url.startswith("https://"),
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE)


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=get_settings().session_days * 86400)
    except BadSignature:
        return None
    user = db.get(User, data.get("uid"))
    if user is None or user.disabled or user.telegram_id != data.get("tg"):
        return None
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user
