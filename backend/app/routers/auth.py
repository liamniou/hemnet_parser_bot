import hashlib
import hmac
import html
import logging
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import clear_session, set_session
from app.config import get_settings
from app.db import get_db
from app.models import LoginRequest, User, utcnow
from app.schemas import UserOut
from app.services import emailer

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_CODE_ATTEMPTS = 5
# Mail-sending limits, to keep the form from being used to spam an inbox.
PER_EMAIL_INTERVAL = timedelta(seconds=60)
PER_EMAIL_PER_HOUR = 5
GLOBAL_PER_HOUR = 200


class EmailIn(BaseModel):
    email: str = Field(max_length=255)


class CodeIn(BaseModel):
    email: str = Field(max_length=255)
    code: str = Field(max_length=16)


class LinkIn(BaseModel):
    token: str = Field(max_length=64)


def normalize(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address")
    return email


def _hash(token: str, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{token}:{code}".encode(), hashlib.sha256).hexdigest()


def _ttl() -> timedelta:
    return timedelta(minutes=get_settings().login_code_minutes)


def upsert_user(db: Session, email: str) -> User:
    s = get_settings()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        # Without configured admins, the very first user to sign in becomes admin.
        if not s.admin_emails and db.scalar(select(func.count()).select_from(User)) == 0:
            user.is_admin = True
        db.add(user)
    if email in s.admin_emails:
        user.is_admin = True
    db.flush()
    return user


def _login(db: Session, req: LoginRequest, response: Response) -> dict:
    req.consumed = True
    user = upsert_user(db, req.email)
    if user.disabled:
        db.commit()
        raise HTTPException(403, "This account is disabled")
    user.last_login_at = utcnow()
    db.commit()
    set_session(response, user)
    return {"status": "ok", "user": UserOut.model_validate(user)}


@router.post("/email")
def start_email_login(body: EmailIn, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.smtp_enabled:
        raise HTTPException(503, "Email is not configured on this server")
    email = normalize(body.email)
    now = utcnow()
    db.query(LoginRequest).filter(LoginRequest.created_at < now - timedelta(days=1)).delete()
    recent = db.scalars(
        select(LoginRequest.created_at).where(
            LoginRequest.email == email, LoginRequest.created_at > now - timedelta(hours=1)
        )
    ).all()
    if recent and max(recent) > now - PER_EMAIL_INTERVAL:
        raise HTTPException(429, "A code was just sent. Wait a minute before requesting another.")
    hour_total = db.scalar(
        select(func.count()).where(LoginRequest.created_at > now - timedelta(hours=1))
    )
    if len(recent) >= PER_EMAIL_PER_HOUR or hour_total >= GLOBAL_PER_HOUR:
        raise HTTPException(429, "Too many sign-in emails. Try again later.")

    token = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    link = f"{s.public_url.rstrip('/')}/login?token={token}"
    minutes = s.login_code_minutes
    try:
        emailer.send_email(
            email,
            f"Hemnet Watch sign-in code: {code}",
            '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.5">'
            f"<p>Your Hemnet Watch sign-in code is</p>"
            f'<p style="font-size:28px;font-weight:700;letter-spacing:4px">{code}</p>'
            f'<p>Or <a href="{html.escape(link)}">click here to sign in</a>.</p>'
            f'<p style="color:#6b7280">The code expires in {minutes} minutes. '
            "If you didn't request it, ignore this email.</p></div>",
            f"Your Hemnet Watch sign-in code is {code}\n\nOr open: {link}\n\n"
            f"The code expires in {minutes} minutes.",
        )
    except Exception as e:
        log.exception("Sending login email failed")
        raise HTTPException(502, "Could not send the email. Try again later.") from e
    db.add(LoginRequest(token=token, email=email, code_hash=_hash(token, code), created_at=now))
    db.commit()
    return {"sent": True, "expires_in": minutes * 60}


@router.post("/email/verify")
def verify_code(body: CodeIn, response: Response, db: Session = Depends(get_db)):
    email = normalize(body.email)
    req = db.scalar(
        select(LoginRequest)
        .where(
            LoginRequest.email == email,
            LoginRequest.consumed.is_(False),
            LoginRequest.created_at > utcnow() - _ttl(),
        )
        .order_by(LoginRequest.created_at.desc())
    )
    if req is None or req.attempts >= MAX_CODE_ATTEMPTS:
        raise HTTPException(400, "The code has expired. Request a new one.")
    req.attempts += 1
    if not hmac.compare_digest(req.code_hash, _hash(req.token, body.code.strip())):
        db.commit()
        raise HTTPException(400, "Wrong code")
    return _login(db, req, response)


@router.post("/email/link")
def verify_link(body: LinkIn, response: Response, db: Session = Depends(get_db)):
    # POSTed by the SPA, so mail scanners that prefetch the link can't consume it.
    req = db.get(LoginRequest, body.token)
    if req is None or req.consumed or req.created_at < utcnow() - _ttl():
        raise HTTPException(400, "This sign-in link has expired. Request a new one.")
    return _login(db, req, response)


@router.post("/dev-login")
def dev_login(email: str, response: Response, db: Session = Depends(get_db)):
    if not get_settings().dev_login:
        raise HTTPException(404)
    user = upsert_user(db, normalize(email))
    user.last_login_at = utcnow()
    db.commit()
    set_session(response, user)
    return UserOut.model_validate(user)


@router.post("/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}
