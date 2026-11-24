import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import clear_session, current_user
from app.db import get_db
from app.models import Notification, User
from app.schemas import NotificationOut, UserOut, UserUpdate
from app.services import notifications

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("", response_model=UserOut)
def update_me(body: UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    if body.name is not None:
        user.name = body.name.strip() or None
    if body.notify_email is not None:
        user.notify_email = body.notify_email
    db.commit()
    return user


@router.post("/test-notification")
def test_notification(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ref = secrets.token_hex(4)
    added = notifications.add_for_user(db, user, None, "test", None, ref=ref)
    db.commit()
    if not added:
        raise HTTPException(400, "Email notifications are turned off or not configured")
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
