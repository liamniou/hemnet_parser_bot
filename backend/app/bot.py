"""Telegram bot long-polling loop.

The bot is only used for: confirming web logins (deep link ``/start login_<token>``),
delivering notifications, and handling the inline "Save" button on notifications.
"""

import html
import logging
import threading
import time
from datetime import timedelta

from app.config import get_settings
from app.db import session_scope
from app.models import Listing, LoginRequest, User, UserListing, utcnow
from app.services import telegram

log = logging.getLogger(__name__)

LOGIN_TTL = timedelta(minutes=10)


def upsert_user(db, tg_user: dict) -> User:
    s = get_settings()
    user = db.query(User).filter(User.telegram_id == tg_user["id"]).one_or_none()
    if user is None:
        user = User(telegram_id=tg_user["id"])
        db.add(user)
        # Without configured admins, the very first user to sign in becomes admin.
        if not s.admin_telegram_ids and db.query(User).count() == 0:
            user.is_admin = True
    user.username = tg_user.get("username")
    user.first_name = tg_user.get("first_name")
    user.last_name = tg_user.get("last_name")
    if tg_user["id"] in s.admin_telegram_ids:
        user.is_admin = True
    user.telegram_blocked = False
    db.flush()
    return user


def _login_keyboard(token: str) -> dict:
    return {"inline_keyboard": [[{"text": "✅ Confirm login", "callback_data": f"login:{token}"}]]}


def handle_update(api: telegram.TelegramAPI, update: dict) -> None:
    s = get_settings()
    if msg := update.get("message"):
        chat_id = msg["chat"]["id"]
        if msg["chat"].get("type") != "private":
            return
        text = (msg.get("text") or "").strip()
        if text.startswith("/start login_"):
            token = text.split("login_", 1)[1]
            with session_scope() as db:
                req = db.get(LoginRequest, token)
                valid = req and not req.consumed and utcnow() - req.created_at < LOGIN_TTL
            if valid:
                api.send_message(
                    chat_id,
                    "Someone (hopefully you) is signing in to <b>Hemnet Watch</b> "
                    "with this Telegram account. Confirm only if you started the login.",
                    reply_markup=_login_keyboard(token),
                )
            else:
                api.send_message(chat_id, "This login link has expired. Please try again.")
            return
        with session_scope() as db:
            user = db.query(User).filter(User.telegram_id == msg["from"]["id"]).one_or_none()
            if user:
                user.telegram_blocked = False
        url = html.escape(s.public_url)
        api.send_message(
            chat_id,
            "👋 This bot delivers Hemnet Watch notifications.\n"
            f'Manage your searches at <a href="{url}">{url}</a>.',
        )
        return

    if cq := update.get("callback_query"):
        data = cq.get("data") or ""
        answer = "Done"
        if data.startswith("login:"):
            token = data.split(":", 1)[1]
            with session_scope() as db:
                req = db.get(LoginRequest, token)
                if req and not req.consumed and utcnow() - req.created_at < LOGIN_TTL:
                    user = upsert_user(db, cq["from"])
                    req.user_id, req.approved_at = user.id, utcnow()
                    answer = "Logged in"
                    ok = True
                else:
                    answer, ok = "Login link expired", False
            if cq.get("message"):
                try:
                    api.call(
                        "editMessageText",
                        chat_id=cq["message"]["chat"]["id"],
                        message_id=cq["message"]["message_id"],
                        text="✅ Logged in. You can return to the browser."
                        if ok
                        else "⌛ This login link has expired.",
                    )
                except telegram.TelegramError:
                    pass
        elif data.startswith("fav:"):
            listing_id = data.split(":", 1)[1]
            with session_scope() as db:
                user = db.query(User).filter(User.telegram_id == cq["from"]["id"]).one_or_none()
                if user and db.get(Listing, listing_id):
                    state = db.get(UserListing, (user.id, listing_id))
                    if state is None:
                        state = UserListing(user_id=user.id, listing_id=listing_id)
                        db.add(state)
                    state.favorite = not state.favorite
                    answer = "⭐ Saved" if state.favorite else "Removed from saved"
                else:
                    answer = "Unknown listing"
        api.call("answerCallbackQuery", callback_query_id=cq["id"], text=answer)
        return

    if mcm := update.get("my_chat_member"):
        status = mcm.get("new_chat_member", {}).get("status")
        with session_scope() as db:
            user = db.query(User).filter(User.telegram_id == mcm["from"]["id"]).one_or_none()
            if user:
                user.telegram_blocked = status in ("kicked", "left")


class BotPoller:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if get_settings().telegram_enabled and get_settings().telegram_polling:
            self._thread = threading.Thread(target=self._run, name="telegram-bot", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        api = telegram.get_api()
        assert api is not None
        try:
            api.call("deleteWebhook")
        except Exception as e:
            log.warning("deleteWebhook failed: %s", e)
        offset: int | None = None
        while not self._stop.is_set():
            try:
                updates = api.call(
                    "getUpdates",
                    offset=offset,
                    timeout=50,
                    allowed_updates=["message", "callback_query", "my_chat_member"],
                )
            except Exception as e:
                log.warning("getUpdates failed: %s", e)
                time.sleep(5)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    handle_update(api, update)
                except Exception:
                    log.exception("Failed to handle update %s", update.get("update_id"))
