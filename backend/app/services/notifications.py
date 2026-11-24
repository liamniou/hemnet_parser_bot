import html
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import (
    Listing,
    ListingRegion,
    Notification,
    SavedSearch,
    User,
    UserListing,
    utcnow,
)
from app.services import emailer
from app.services.matching import Criteria, matches

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


def _channels(user: User) -> list[str]:
    return ["email"] if user.notify_email and get_settings().smtp_enabled else []


def add_for_user(
    db: Session, user: User, listing_id: str | None, kind: str, search_id: int | None, ref: str = ""
) -> int:
    added = 0
    for channel in _channels(user):
        key = f"{kind}:{user.id}:{listing_id}:{channel}:{ref}"
        if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)):
            continue
        db.add(
            Notification(
                user_id=user.id,
                listing_id=listing_id,
                search_id=search_id,
                kind=kind,
                channel=channel,
                dedupe_key=key,
            )
        )
        added += 1
    return added


def _active_searches(db: Session) -> list[SavedSearch]:
    return list(
        db.scalars(
            select(SavedSearch)
            .join(User)
            .where(SavedSearch.enabled.is_(True), User.disabled.is_(False))
        )
    )


def region_ids_for(db: Session, listing_id: str) -> set[int]:
    return set(
        db.scalars(select(ListingRegion.region_id).where(ListingRegion.listing_id == listing_id))
    )


def enqueue_new_listing(db: Session, listing: Listing) -> int:
    regions = region_ids_for(db, listing.id)
    added = 0
    notified_users: set[int] = set()
    for search in _active_searches(db):
        if not search.notify_new or search.user_id in notified_users:
            continue
        if matches(Criteria.from_search(search), listing, regions):
            notified_users.add(search.user_id)
            added += add_for_user(db, search.user, listing.id, "new", search.id)
    return added


def enqueue_followup(db: Session, listing: Listing, kind: str, ref: str = "") -> int:
    """Price drops / sold events go to users who were told about the listing or saved it."""
    flag = {"price_drop": SavedSearch.notify_price_drop, "sold": SavedSearch.notify_sold}[kind]
    recipients: dict[int, int | None] = {}
    rows = db.execute(
        select(Notification.user_id, Notification.search_id)
        .join(SavedSearch, SavedSearch.id == Notification.search_id)
        .where(
            Notification.listing_id == listing.id,
            Notification.kind == "new",
            SavedSearch.enabled.is_(True),
            flag.is_(True),
        )
    )
    for user_id, search_id in rows:
        recipients.setdefault(user_id, search_id)
    for user_id in db.scalars(
        select(UserListing.user_id).where(
            UserListing.listing_id == listing.id, UserListing.favorite.is_(True)
        )
    ):
        recipients.setdefault(user_id, None)

    added = 0
    for user_id, search_id in recipients.items():
        user = db.get(User, user_id)
        if user and not user.disabled:
            added += add_for_user(db, user, listing.id, kind, search_id, ref)
    return added


# ---------------------------------------------------------------- rendering


def _fmt_int(v: int | None, suffix: str = "") -> str | None:
    return f"{v:,}".replace(",", " ") + suffix if v is not None else None


def _fmt_num(v: float | None) -> str | None:
    if v is None:
        return None
    return str(int(v)) if float(v).is_integer() else str(v).replace(".", ",")


def listing_summary_lines(listing: Listing) -> list[str]:
    facts = [
        listing.asking_price_text or _fmt_int(listing.asking_price, " kr"),
        f"{_fmt_num(listing.rooms)} rum" if listing.rooms else None,
        f"{_fmt_num(listing.living_area)} m²" if listing.living_area else None,
        f"{_fmt_int(listing.fee, ' kr/mån')}" if listing.fee else None,
    ]
    extra = [
        f"{_fmt_int(listing.sqm_price, ' kr/m²')}" if listing.sqm_price else None,
        f"vån {listing.floor}" if listing.floor and "vån" not in listing.floor else listing.floor,
        f"byggår {listing.year_built}" if listing.year_built else None,
        "balkong" if listing.has_balcony or "BALCONY" in (listing.labels or []) else None,
    ]
    return [" · ".join(x for x in facts if x), " · ".join(x for x in extra if x)]


def _photo_url(listing: Listing) -> str | None:
    if listing.thumbnails:
        return listing.thumbnails[0]
    if listing.image_urls:
        return listing.image_urls[0]
    return None


def render(n: Notification) -> tuple[str, str, str]:
    """Returns (subject, html, plain text)."""
    s = get_settings()
    listing = n.listing
    if listing is None:
        text = "✅ Test notification from Hemnet Watch. Notifications are working!"
        return "Hemnet Watch test notification", html.escape(text), text

    e = html.escape
    title = ", ".join(x for x in (listing.street_address, listing.location_description) if x)
    archive = f"{s.public_url.rstrip('/')}/listings/{listing.id}"
    lines1, lines2 = listing_summary_lines(listing)

    if n.kind == "new":
        head = "🏠 <b>New listing</b>"
        subject = f"New: {title} – {listing.asking_price_text or ''}".strip(" –")
    elif n.kind == "price_drop":
        changes = listing.price_changes
        old = changes[-1].old_price if changes else None
        old_txt = _fmt_int(old, " kr") or "?"
        new_txt = _fmt_int(listing.asking_price, " kr") or "?"
        head = f"📉 <b>Price drop</b>: {e(old_txt)} → {e(new_txt)}"
        subject = f"Price drop: {title}"
    else:
        price = listing.sold_price_text or _fmt_int(listing.sold_price, " kr") or "n/a"
        change = f" ({listing.sold_price_change})" if listing.sold_price_change else ""
        head = f"🔨 <b>Sold for {e(price)}</b>{e(change)}"
        subject = f"Sold: {title} – {price}{change}"

    search_line = f"\n🔎 {e(n.search.name)}" if n.search else ""
    links = f'<a href="{e(listing.url)}">Hemnet</a> · <a href="{e(archive)}">Archive</a>'
    if listing.lat and listing.lon:
        maps = f"https://www.google.com/maps/search/?api=1&query={listing.lat},{listing.lon}"
        links += f' · <a href="{maps}">Map</a>'
    body = (
        f"{head}\n<b>{e(title)}</b>\n{e(lines1)}\n"
        + (f"{e(lines2)}\n" if lines2 else "")
        + f"{search_line}\n{links}".lstrip("\n")
    )
    text = f"{subject}\n{lines1}\n{lines2}\n{listing.url}\n{archive}"
    return subject, body, text


def _email_html(body: str, listing: Listing | None) -> str:
    img = ""
    if listing and (photo := _photo_url(listing)):
        style = "max-width:560px;width:100%;border-radius:8px"
        img = f'<p><img src="{html.escape(photo)}" style="{style}"></p>'
    return (
        '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.5">'
        f"{img}{body.replace(chr(10), '<br>')}</div>"
    )


# ---------------------------------------------------------------- dispatch


def _claim(notification_id: int) -> bool:
    """Atomically move pending -> sending so concurrent dispatchers never double-send."""
    with session_scope() as db:
        res = db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.status == "pending")
            .values(status="sending")
        )
        return res.rowcount == 1


def send_notification(notification_id: int) -> None:
    if not _claim(notification_id):
        return
    with session_scope() as db:
        n = db.get(Notification, notification_id)
        n.status = "pending"  # failures below fall back to pending for a retry
        user = db.get(User, n.user_id)
        _ = n.listing, n.search, n.listing.price_changes if n.listing else None
        subject, body, text = render(n)
        n.attempts += 1
        try:
            emailer.send_email(user.email, subject, _email_html(body, n.listing), text)
            n.status, n.sent_at, n.error = "sent", utcnow(), None
        except Exception as e:
            log.exception("Notification %s failed", n.id)
            n.error = str(e)
            if n.attempts >= MAX_ATTEMPTS:
                n.status = "failed"


def dispatch_pending(limit: int = 50) -> int:
    with session_scope() as db:
        ids = list(
            db.scalars(
                select(Notification.id)
                .where(
                    Notification.status == "pending",
                    Notification.created_at > utcnow() - timedelta(days=2),
                )
                .order_by(Notification.id)
                .limit(limit)
            )
        )
    for nid in ids:
        send_notification(nid)
    return len(ids)


def notify_admins(text: str) -> None:
    if not get_settings().smtp_enabled:
        return
    with session_scope() as db:
        admins = list(
            db.scalars(select(User.email).where(User.is_admin.is_(True), User.disabled.is_(False)))
        )
    for email in admins:
        try:
            emailer.send_email(email, f"Hemnet Watch: {text[:80]}", html.escape(text), text)
        except Exception as e:
            log.warning("Admin notification failed: %s", e)
