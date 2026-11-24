import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.auth import clear_session, set_session
from app.bot import LOGIN_TTL, upsert_user
from app.config import get_settings
from app.db import get_db
from app.models import LoginRequest, User, utcnow
from app.schemas import UserOut
from app.services import telegram

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram")
def start_telegram_login(db: Session = Depends(get_db)):
    username = telegram.bot_username()
    if not username:
        raise HTTPException(503, "Telegram bot is not configured")
    # Housekeeping: drop stale requests.
    db.query(LoginRequest).filter(LoginRequest.created_at < utcnow() - LOGIN_TTL * 6).delete()
    token = secrets.token_urlsafe(24)
    db.add(LoginRequest(token=token))
    db.commit()
    return {
        "token": token,
        "url": f"https://t.me/{username}?start=login_{token}",
        "expires_in": int(LOGIN_TTL.total_seconds()),
    }


@router.get("/telegram/{token}")
def poll_telegram_login(token: str, response: Response, db: Session = Depends(get_db)):
    req = db.get(LoginRequest, token)
    if req is None or req.consumed or utcnow() - req.created_at > LOGIN_TTL:
        raise HTTPException(410, "Login request expired")
    if req.user_id is None:
        return {"status": "pending"}
    user = db.get(User, req.user_id)
    if user is None or user.disabled:
        raise HTTPException(403, "Account disabled")
    req.consumed = True
    user.last_login_at = utcnow()
    db.commit()
    set_session(response, user)
    return {"status": "ok", "user": UserOut.model_validate(user)}


@router.post("/dev-login")
def dev_login(telegram_id: int, response: Response, db: Session = Depends(get_db)):
    if not get_settings().dev_login:
        raise HTTPException(404)
    user = upsert_user(db, {"id": telegram_id, "first_name": f"Dev {telegram_id}"})
    user.last_login_at = utcnow()
    db.commit()
    set_session(response, user)
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}
