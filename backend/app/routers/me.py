import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import clear_session, current_user
from app.config import get_settings
from app.db import get_db
from app.models import Notification, User, utcnow
from app.schemas import CodeIn, EmailIn, NotificationOut, UserOut, UserUpdate
from app.services import emailer, notifications

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    if body.notify_telegram is not None:
        user.notify_telegram = body.notify_telegram
    if body.notify_email is not None:
        if body.notify_email and not user.email_verified:
            raise HTTPException(400, "Verify your email address first")
        user.notify_email = body.notify_email
    db.commit()
    return user


@router.post("/email", response_model=UserOut)
def set_email(body: EmailIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not get_settings().smtp_enabled:
        raise HTTPException(503, "Email delivery is not configured on this server")
    user = db.merge(user)
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        emailer.send_email(
            body.email,
            "Hemnet Watch: confirm your email",
            f"<p>Your confirmation code is <b style='font-size:20px'>{code}</b>.</p>"
            "<p>It expires in 30 minutes.</p>",
            f"Your Hemnet Watch confirmation code is {code}. It expires in 30 minutes.",
        )
    except Exception as e:
        raise HTTPException(502, f"Could not send email: {e}") from e
    user.email = body.email.strip()
    user.email_verified = False
    user.notify_email = False
    user.email_code = code
    user.email_code_expires_at = utcnow() + timedelta(minutes=30)
    db.commit()
    return user


@router.post("/email/verify", response_model=UserOut)
def verify_email(body: CodeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    if (
        not user.email_code
        or not user.email_code_expires_at
        or user.email_code_expires_at < utcnow()
        or not secrets.compare_digest(user.email_code, body.code.strip())
    ):
        raise HTTPException(400, "Invalid or expired code")
    user.email_verified = True
    user.notify_email = True
    user.email_code = None
    db.commit()
    return user


@router.delete("/email", response_model=UserOut)
def remove_email(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    user.email, user.email_verified, user.notify_email, user.email_code = None, False, False, None
    db.commit()
    return user


@router.post("/test-notification")
def test_notification(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ref = secrets.token_hex(4)
    added = notifications.add_for_user(db, user, None, "test", None, ref=ref)
    db.commit()
    if not added:
        raise HTTPException(400, "No notification channel is enabled")
    ids = list(
        db.scalars(select(Notification.id).where(Notification.dedupe_key.endswith(f":{ref}")))
    )
    for nid in ids:
        notifications.send_notification(nid)
    db.expire_all()
    rows = db.scalars(select(Notification).where(Notification.id.in_(ids))).all()
    return [{"channel": n.channel, "status": n.status, "error": n.error} for n in rows]


@router.get("/notifications", response_model=list[NotificationOut])
def my_notifications(
    limit: int = 100, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(min(limit, 500))
    ).all()
    out = []
    for n in rows:
        item = NotificationOut.model_validate(n)
        if n.listing:
            item.listing_title = ", ".join(
                x for x in (n.listing.street_address, n.listing.location_description) if x
            )
        if n.search:
            item.search_name = n.search.name
        out.append(item)
    return out


@router.delete("")
def delete_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from fastapi.responses import JSONResponse

    db.delete(db.merge(user))
    db.commit()
    resp = JSONResponse({"ok": True})
    clear_session(resp)
    return resp
