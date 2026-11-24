import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class TelegramError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code

    @property
    def blocked(self) -> bool:
        return self.code == 403


class TelegramAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.client = httpx.Client(timeout=httpx.Timeout(70.0, connect=10.0))

    def call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        r = self.client.post(f"{self.base}/{method}", json=payload)
        data = r.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", r.text), data.get("error_code"))
        return data["result"]

    def send_message(self, chat_id: int, text: str, **kw: Any) -> dict:
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
            **kw,
        )

    def send_photo(self, chat_id: int, photo: str, caption: str, **kw: Any) -> dict:
        return self.call(
            "sendPhoto", chat_id=chat_id, photo=photo, caption=caption, parse_mode="HTML", **kw
        )


_api: TelegramAPI | None = None


def get_api() -> TelegramAPI | None:
    global _api
    s = get_settings()
    if not s.telegram_enabled:
        return None
    if _api is None:
        _api = TelegramAPI(s.telegram_bot_token)
    return _api


def set_api(api: TelegramAPI | None) -> None:
    global _api
    _api = api


_bot_username: str | None = None


def bot_username() -> str:
    global _bot_username
    s = get_settings()
    if s.telegram_bot_username:
        return s.telegram_bot_username.lstrip("@")
    if _bot_username is None and (api := get_api()):
        try:
            _bot_username = api.call("getMe")["username"]
        except Exception as e:
            log.error("getMe failed: %s", e)
            return ""
    return _bot_username or ""
