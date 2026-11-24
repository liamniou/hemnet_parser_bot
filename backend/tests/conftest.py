import json
import os
from collections.abc import Callable
from typing import Any

import pytest

os.environ.update(
    {
        "SCHEDULER_ENABLED": "false",
        "TELEGRAM_POLLING": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "SMTP_HOST": "",
        "SECRET_KEY": "test-secret-key-0123456789",
        "REQUEST_DELAY_SECONDS": "0",
    }
)


def rsc_html(*objects: Any) -> str:
    """Wrap objects the way Next.js streams them: JSON inside self.__next_f.push string chunks."""
    payload = "0:" + json.dumps(list(objects), ensure_ascii=False, separators=(",", ":")) + "\n"
    half = len(payload) // 2
    chunks = [payload[:half], payload[half:]]
    scripts = "".join(f"<script>self.__next_f.push({json.dumps([1, c])})</script>" for c in chunks)
    return f"<html><body>{scripts}</body></html>"


def make_card(lid: str, **over: Any) -> dict:
    card = {
        "__typename": "ListingCard",
        "id": lid,
        "slug": f"lagenhet-2rum-sodermalm-stockholms-kommun-gatan-1-{lid}",
        "recordType": "COMMON",
        "askingPrice": "3 495 000 kr",
        "fee": "3 200 kr/mån",
        "squareMeterPrice": "75 978 kr/m²",
        "livingAndSupplementalAreas": "46 m²",
        "landArea": None,
        "rooms": "2 rum",
        "floor": "vån 3/5",
        "streetAddress": "Gatan 1",
        "locationDescription": "Södermalm, Stockholms kommun",
        "coordinates": {"__typename": "GeometryPoint", "lat": 59.31, "long": 18.07},
        "housingForm": {"__typename": "HousingForm", "symbol": "APARTMENT", "name": "Lägenhet"},
        "labels": [{"__typename": "Label", "identifier": "BALCONY", "text": "Balkong"}],
        "newConstruction": False,
        "upcoming": False,
        "publishedAt": "1795441712.0",
        "brokerName": "Anna",
        "brokerAgencyName": "Mäklarbyrån",
        "description": "Ljus tvåa",
        "thumbnails": [f"https://bilder.hemnet.se/images/itemgallery_cut/aa/bb/{lid}.jpg"],
    }
    card.update(over)
    return card


def search_html(cards: list[dict], total: int | None = None) -> str:
    result = {
        "__typename": "ListingResultsCombined",
        "total": len(cards) if total is None else total,
        "cards": cards,
    }
    # Recommendation cards outside the result list must be ignored.
    stray = make_card("99999999")
    return rsc_html({"x": stray}, {"searchResult": result})


class FakeHemnet:
    """Stands in for HemnetClient; tests mutate `pages`, `details` and `sales`."""

    def __init__(self) -> None:
        self.pages: list[list[dict]] = [[]]
        self.since_pages: list[list[dict]] | None = None
        self.details: dict[str, Callable[[], Any]] = {}
        self.sales: list[Any] = []
        self.total_override: int | None = None
        self.calls: list[tuple] = []

    def search(self, location_id, item_types, page=1, published_since=None):
        from app.hemnet.parse import parse_search

        self.calls.append(("search", location_id, page, published_since))
        pages = self.since_pages if published_since and self.since_pages is not None else self.pages
        cards = pages[page - 1] if page <= len(pages) else []
        total = self.total_override or sum(len(p) for p in pages)
        return parse_search(search_html(cards, total))

    def detail(self, slug, listing_id):
        from app.hemnet.parse import DetailData

        self.calls.append(("detail", listing_id))
        if listing_id in self.details:
            return self.details[listing_id]()
        return DetailData("active", listing_id, {"year_built": 1930, "districts": ["Södermalm"]})

    def sold(self, location_id, item_types, page=1):
        self.calls.append(("sold", location_id, page))
        return (len(self.sales), self.sales if page == 1 else [])

    def locations(self, q):
        from app.hemnet.parse import Location

        return [Location("18031", "Stockholms kommun", "municipality", "Stockholms län")]

    def download(self, url):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (2048, 1365), (120, 160, 200)).save(buf, "JPEG")
        return buf.getvalue()


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db import init_engine
    from app.hemnet import client as client_mod
    from app.services import telegram

    init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    fake = FakeHemnet()
    client_mod.set_client(fake)
    telegram.set_api(None)
    yield fake
    client_mod.set_client(None)
    telegram.set_api(None)
    get_settings.cache_clear()


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.fail_with = None

    def call(self, method: str, **params: Any) -> Any:
        if self.fail_with:
            raise self.fail_with
        self.sent.append((method, params))
        if method == "getMe":
            return {"username": "hemnet_test_bot"}
        return {"message_id": len(self.sent)}

    def send_message(self, chat_id, text, **kw):
        return self.call("sendMessage", chat_id=chat_id, text=text, **kw)

    def send_photo(self, chat_id, photo, caption, **kw):
        return self.call("sendPhoto", chat_id=chat_id, photo=photo, caption=caption, **kw)


@pytest.fixture()
def tg(app_env, monkeypatch):
    from app.config import get_settings
    from app.services import telegram

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "hemnet_test_bot")
    get_settings.cache_clear()
    fake = FakeTelegram()
    telegram.set_api(fake)
    return fake
