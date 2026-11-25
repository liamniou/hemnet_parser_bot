import json
import os
from collections.abc import Callable
from typing import Any

import pytest

os.environ.update(
    {
        "SCHEDULER_ENABLED": "false",
        "SMTP_HOST": "",
        "ADMIN_EMAILS": "",
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
        self.polygons: dict[str, list] = {}
        self.location_results: dict[str, list] = {}

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

        self.calls.append(("locations", q))
        if q in self.location_results:
            return self.location_results[q]
        return [Location("18031", "Stockholms kommun", "municipality", "Stockholms län")]

    def location_polygons(self, location_id):
        self.calls.append(("polygons", location_id))
        return self.polygons.get(location_id, [])

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

    init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    fake = FakeHemnet()
    client_mod.set_client(fake)
    yield fake
    client_mod.set_client(None)
    get_settings.cache_clear()


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail_with: Exception | None = None

    def __call__(self, to: str, subject: str, html: str, text: str) -> None:
        if self.fail_with:
            raise self.fail_with
        self.sent.append({"to": to, "subject": subject, "html": html, "text": text})

    def last_code(self, to: str) -> str:
        import re

        msg = next(m for m in reversed(self.sent) if m["to"] == to.strip().lower())
        return re.search(r"code: (\d{6})", msg["subject"]).group(1)

    def last_link_token(self, to: str) -> str:
        import re

        msg = next(m for m in reversed(self.sent) if m["to"] == to.strip().lower())
        return re.search(r"token=([\w-]+)", msg["text"]).group(1)


@pytest.fixture()
def mail(app_env, monkeypatch):
    from app.config import get_settings
    from app.services import emailer

    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_FROM", "Hemnet Watch <hw@test>")
    get_settings.cache_clear()
    fake = FakeMailer()
    monkeypatch.setattr(emailer, "send_email", fake)
    return fake
