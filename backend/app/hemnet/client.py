import logging
import threading
import time
from typing import Any
from urllib.parse import urlencode

from curl_cffi import requests as cffi

from app.hemnet import parse

log = logging.getLogger(__name__)

BASE = "https://www.hemnet.se"

# Hemnet `item_types[]` query values -> human labels (used by the admin UI).
ITEM_TYPES = {
    "bostadsratt": "Lägenhet (bostadsrätt)",
    "villa": "Villa",
    "radhus": "Radhus / parhus / kedjehus",
    "fritidshus": "Fritidshus",
    "tomt": "Tomt",
    "gard": "Gård/skog",
    "other": "Övrigt",
}


MAP_BOUNDS_QUERY = (
    "query webMapBounds($locationIds: [ID!]) "
    "{ mapBounds(locationIds: $locationIds) { locationPolygons { coordinates } } }"
)


class HemnetError(Exception):
    pass


class NotFound(HemnetError):
    pass


class HemnetClient:
    """Thin client for hemnet.se.

    Hemnet sits behind Cloudflare, which rejects default Python TLS fingerprints. curl_cffi
    impersonates a real Chrome TLS/HTTP2 fingerprint, which is enough for plain page loads.
    All page requests are serialized and throttled to stay polite.
    """

    def __init__(self, delay: float = 2.0, retries: int = 3, timeout: float = 30.0):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last = 0.0
        self._session = cffi.Session(impersonate="chrome")

    def _throttle(self, delay: float) -> None:
        wait = self._last + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get(self, url: str, *, delay: float | None = None) -> cffi.Response:
        return self._request("GET", url, delay=delay)

    def _request(
        self, method: str, url: str, *, delay: float | None = None, **kw: Any
    ) -> cffi.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            with self._lock:
                self._throttle(self.delay if delay is None else delay)
                try:
                    r = self._session.request(
                        method, url, timeout=self.timeout, allow_redirects=True, **kw
                    )
                except Exception as e:  # network errors
                    last_exc = e
                    r = None
            if r is not None:
                if r.status_code == 404:
                    raise NotFound(url)
                if r.status_code == 200:
                    return r
                last_exc = HemnetError(f"HTTP {r.status_code} for {url}")
            log.warning(
                "%s %s failed (attempt %s/%s): %s", method, url, attempt, self.retries, last_exc
            )
            if attempt < self.retries:
                time.sleep(5 * attempt)
                if r is not None and r.status_code == 403:
                    # Fresh session (new cookies) usually clears a Cloudflare challenge.
                    self._session = cffi.Session(impersonate="chrome")
        raise HemnetError(str(last_exc))

    @staticmethod
    def search_url(
        location_id: str,
        item_types: list[str],
        page: int = 1,
        published_since: str | None = None,
        sold: bool = False,
    ) -> str:
        params: list[tuple[str, str]] = [("location_ids[]", location_id)]
        params += [("item_types[]", t) for t in item_types]
        if published_since:
            params.append(("published_since", published_since))
        if page > 1:
            params.append(("page", str(page)))
        path = "/salda/bostader" if sold else "/bostader"
        return f"{BASE}{path}?{urlencode(params)}"

    def search(
        self,
        location_id: str,
        item_types: list[str],
        page: int = 1,
        published_since: str | None = None,
    ) -> parse.SearchPage:
        r = self.get(self.search_url(location_id, item_types, page, published_since))
        return parse.parse_search(r.text)

    def sold(
        self, location_id: str, item_types: list[str], page: int = 1
    ) -> tuple[int, list[parse.SaleData]]:
        r = self.get(self.search_url(location_id, item_types, page, sold=True))
        return parse.parse_sold_search(r.text)

    def detail(self, slug: str, listing_id: str) -> parse.DetailData:
        try:
            r = self.get(f"{BASE}/bostad/{slug}")
        except NotFound:
            return parse.DetailData("removed", listing_id)
        return parse.parse_detail(r.text, listing_id)

    def locations(self, query: str) -> list[parse.Location]:
        r = self.get(f"{BASE}/locations/show?{urlencode({'q': query})}", delay=0.5)
        return parse.parse_locations(r.json())

    def location_polygons(self, location_id: str) -> list[list]:
        """Outline of a Hemnet location, exactly as hemnet.se draws it on its map.

        Returns a list of GeoJSON polygon coordinate arrays (rings of [lon, lat])."""
        r = self._request(
            "POST",
            f"{BASE}/graphql",
            delay=1.0,
            json={
                "operationName": "webMapBounds",
                "query": MAP_BOUNDS_QUERY,
                "variables": {"locationIds": [location_id]},
            },
            # Cloudflare rejects GraphQL calls that don't look like they come from the site.
            headers={"origin": BASE, "referer": f"{BASE}/bostader"},
        )
        data = r.json()
        if data.get("errors") or not data.get("data"):
            raise HemnetError(f"mapBounds failed: {data.get('errors')}")
        polys = (data["data"].get("mapBounds") or {}).get("locationPolygons") or []
        return [p["coordinates"] for p in polys if p.get("coordinates")]

    def download(self, url: str) -> bytes:
        return self.get(url, delay=0.2).content


_client: HemnetClient | None = None
_image_client: HemnetClient | None = None


def get_client() -> HemnetClient:
    global _client
    if _client is None:
        from app.config import get_settings

        _client = HemnetClient(delay=get_settings().request_delay_seconds)
    return _client


def get_image_client() -> HemnetClient:
    """Images come from the bilder.hemnet.se CDN; a separate client keeps downloads from
    queueing behind throttled page requests."""
    global _image_client
    if _image_client is None:
        _image_client = HemnetClient(delay=0.1)
    return _image_client


def set_client(client: HemnetClient | None) -> None:
    global _client, _image_client
    _client = _image_client = client
