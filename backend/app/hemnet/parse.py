"""Parsers for hemnet.se pages.

Hemnet is a Next.js App Router site: page data is streamed as React Server Component
payload chunks (``self.__next_f.push([1, "..."])``). The chunks contain GraphQL-shaped
JSON objects tagged with ``__typename`` which we locate and decode directly.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.S)
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_TEXT_ROW_RE = re.compile(r"(?:^|\n)([0-9a-f]+):T([0-9a-f]+),")
_JSON_ROW_RE = re.compile(r"(?:^|\n)([0-9a-f]+):(?=[\[{\"])")
# "$<row>" or "$<row>:<key>:<index>:..." (a path into an already-streamed row).
_REF_RE = re.compile(r"^\$([0-9a-f]+)((?::[^:]+)*)$")
_ELEMENT_FIELDS = {"type": "1", "key": "2", "props": "3"}


class ParseError(Exception):
    pass


def extract_rsc(html: str) -> str:
    out: list[str] = []
    for chunk in _PUSH_RE.findall(html):
        try:
            arr = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            out.append(arr[1])
    return "".join(out)


class Rows:
    """The rows of an RSC payload, used to resolve references between them.

    Long strings are streamed as ``<id>:T<byte length hex>,<text>`` and JSON as ``<id>:<json>``.
    JSON values reference them as ``"$<id>"``; repeated objects are deduplicated into path
    references such as ``"$3b:4:props:result:card:housingForm"``.
    """

    def __init__(self, payload: str):
        self.payload = payload
        self.text: dict[str, str] = {}
        for m in _TEXT_ROW_RE.finditer(payload):
            length = int(m.group(2), 16)
            raw = payload[m.end() : m.end() + length].encode()[:length]
            self.text[m.group(1)] = raw.decode("utf-8", errors="ignore")
        self._json_pos = {m.group(1): m.end() for m in _JSON_ROW_RE.finditer(payload)}
        self._json: dict[str, Any] = {}

    def json_row(self, row_id: str) -> Any:
        if row_id not in self._json:
            pos = self._json_pos.get(row_id)
            value = None
            if pos is not None:
                try:
                    value, _ = json.JSONDecoder().raw_decode(self.payload, pos)
                except json.JSONDecodeError:
                    value = None
            self._json[row_id] = value
        return self._json[row_id]

    def lookup(self, row_id: str, path: list[str], depth: int) -> Any:
        if not path and row_id in self.text:
            return self.text[row_id]
        node = self.json_row(row_id)
        for key in path:
            node = self.resolve(node, depth + 1, shallow=True)
            # React elements are streamed as ["$", type, key, props].
            if isinstance(node, list) and node[:1] == ["$"] and key in _ELEMENT_FIELDS:
                key = _ELEMENT_FIELDS[key]
            if isinstance(node, dict):
                node = node.get(key)
            elif isinstance(node, list) and key.isdigit() and int(key) < len(node):
                node = node[int(key)]
            else:
                return None
        return node

    def resolve(self, obj: Any, depth: int = 0, shallow: bool = False) -> Any:
        if depth > 50:
            return obj
        if isinstance(obj, str):
            if obj.startswith("$$"):
                return obj[1:]
            m = _REF_RE.match(obj)
            if not m:
                return obj
            target = self.lookup(m.group(1), [p for p in m.group(2).split(":") if p], depth)
            if target is None:
                return obj
            return target if shallow else self.resolve(target, depth + 1)
        if shallow:
            return obj
        if isinstance(obj, list):
            return [self.resolve(x, depth + 1) for x in obj]
        if isinstance(obj, dict):
            return {k: self.resolve(v, depth + 1) for k, v in obj.items()}
        return obj


def find_objects(payload: str, typename: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    key = f'{{"__typename":"{typename}"'
    found: list[dict[str, Any]] = []
    idx = 0
    while (i := payload.find(key, idx)) != -1:
        try:
            obj, end = decoder.raw_decode(payload, i)
        except json.JSONDecodeError:
            idx = i + len(key)
            continue
        found.append(obj)
        idx = end
    return found


def _richest(objs: list[dict[str, Any]], **match: Any) -> dict[str, Any] | None:
    """RSC payloads repeat objects with different field subsets; pick the fullest match."""
    cands = [o for o in objs if all(o.get(k) == v for k, v in match.items())]
    return max(cands, key=len) if cands else None


def _digits(text: str) -> str:
    return re.sub(r"[\s\u00a0\u202f]", "", text)


def parse_money(text: str | None) -> int | None:
    """'2 695 000 kr' -> 2695000, 'fr. 1 995 000 kr' -> 1995000, 'Pris saknas' -> None."""
    if not text:
        return None
    m = re.search(r"\d[\d\s\u00a0\u202f]*", text)
    if not m:
        return None
    return int(_digits(m.group(0)))


def parse_number(text: str | None) -> float | None:
    """'46,5 m²' -> 46.5, '1-5 rum' -> 1.0, '2,5 rum' -> 2.5."""
    if not text:
        return None
    m = _NUM_RE.search(_digits(text))
    return float(m.group(0).replace(",", ".")) if m else None


def parse_areas(text: str | None) -> tuple[float | None, float | None]:
    """'58+12 m²' -> (58, 12); '46,5 m²' -> (46.5, None)."""
    if not text:
        return None, None
    parts = _digits(text).split("+")
    living = parse_number(parts[0])
    supplemental = parse_number(parts[1]) if len(parts) > 1 else None
    return living, supplemental


def parse_ts(value: str | float | None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), UTC).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def parse_year(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(1[6-9]\d\d|20\d\d)", text)
    return int(m.group(1)) if m else None


@dataclass
class CardData:
    id: str
    slug: str
    record_type: str | None
    housing_form: str | None
    housing_form_name: str | None
    street_address: str | None
    location_description: str | None
    lat: float | None
    lon: float | None
    asking_price: int | None
    asking_price_text: str | None
    fee: int | None
    sqm_price: int | None
    living_area: float | None
    supplemental_area: float | None
    land_area: float | None
    rooms: float | None
    floor: str | None
    labels: list[str]
    new_construction: bool
    upcoming: bool
    published_at: datetime | None
    broker_name: str | None
    broker_agency: str | None
    description: str | None
    thumbnails: list[str] = field(default_factory=list)

    @property
    def has_balcony(self) -> bool | None:
        return True if "BALCONY" in self.labels else None

    @property
    def has_elevator(self) -> bool | None:
        return True if "ELEVATOR" in self.labels else None


def _dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _text(v: Any) -> str | None:
    """Strings, minus unresolved RSC references."""
    return v if isinstance(v, str) and not _REF_RE.match(v) else None


def parse_card(c: dict[str, Any]) -> CardData:
    living, supplemental = parse_areas(_text(c.get("livingAndSupplementalAreas")))
    coords = _dict(c.get("coordinates"))
    hf = _dict(c.get("housingForm"))
    return CardData(
        id=str(c["id"]),
        slug=c.get("slug") or str(c["id"]),
        record_type=c.get("recordType"),
        housing_form=hf.get("symbol"),
        housing_form_name=hf.get("name"),
        street_address=c.get("streetAddress"),
        location_description=c.get("locationDescription"),
        lat=coords.get("lat"),
        lon=coords.get("long"),
        asking_price=parse_money(c.get("askingPrice")),
        asking_price_text=c.get("askingPrice"),
        fee=parse_money(c.get("fee")),
        sqm_price=parse_money(c.get("squareMeterPrice")),
        living_area=living,
        supplemental_area=supplemental,
        land_area=parse_number(c.get("landArea")),
        rooms=parse_number(c.get("rooms")),
        floor=c.get("floor"),
        labels=[lb["identifier"] for lb in _list(c.get("labels")) if _dict(lb).get("identifier")],
        new_construction=bool(c.get("newConstruction")) or c.get("recordType") == "PROJECT",
        upcoming=bool(c.get("upcoming")),
        published_at=parse_ts(c.get("publishedAt")),
        broker_name=c.get("brokerName"),
        broker_agency=c.get("brokerAgencyName"),
        description=c.get("description"),
        thumbnails=[t for t in _list(c.get("thumbnails")) if _text(t)],
    )


@dataclass
class SearchPage:
    total: int
    cards: list[CardData]


def parse_search(html: str) -> SearchPage:
    payload = extract_rsc(html)
    results = [o for o in find_objects(payload, "ListingResultsCombined") if "cards" in o]
    if not results:
        raise ParseError("ListingResultsCombined not found in search page")
    res = Rows(payload).resolve(max(results, key=lambda o: len(o.get("cards") or [])))
    cards = [parse_card(c) for c in res.get("cards") or [] if isinstance(c, dict) and c.get("id")]
    return SearchPage(total=int(res.get("total") or 0), cards=cards)


@dataclass
class SaleData:
    sale_id: str
    listing_id: str | None
    slug: str
    final_price: int | None
    final_price_text: str | None
    asking_price: int | None
    sold_at: datetime | None
    price_change: str | None


def parse_sold_search(html: str) -> tuple[int, list[SaleData]]:
    payload = extract_rsc(html)
    results = [o for o in find_objects(payload, "SoldListingResults") if "cards" in o]
    if not results:
        raise ParseError("SoldListingResults not found in sold search page")
    res = max(results, key=lambda o: len(o.get("cards") or []))
    sales = []
    for c in res.get("cards") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        sales.append(
            SaleData(
                sale_id=str(c["id"]),
                listing_id=str(c["listingId"]) if c.get("listingId") else None,
                slug=c.get("slug") or "",
                final_price=parse_money(c.get("finalPrice")),
                final_price_text=c.get("finalPrice"),
                asking_price=parse_money(c.get("askingPrice")),
                sold_at=parse_ts(c.get("soldAt")),
                price_change=c.get("priceChange"),
            )
        )
    return int(res.get("total") or 0), sales


def _money(obj: Any) -> int | None:
    if isinstance(obj, dict):
        amount = obj.get("amount")
        return (
            int(amount) if isinstance(amount, (int, float)) else parse_money(obj.get("formatted"))
        )
    return None


def _amenity(listing: dict[str, Any], kind: str) -> bool | None:
    for a in listing.get("relevantAmenities") or []:
        if isinstance(a, dict) and a.get("kind") == kind:
            return a.get("isAvailable")
    return None


def _gallery(listing: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    imgs = listing.get("images")
    items = imgs.get("images") if isinstance(imgs, dict) else imgs
    for group in (items or [], listing.get("floorPlanImages") or []):
        for img in group:
            if not isinstance(img, dict):
                continue
            filename = img.get("filename")
            if filename:
                url = f"https://bilder.hemnet.se/images/original/{filename}"
            elif img.get("url"):
                url = img["url"]
            else:
                continue
            if url not in urls:
                urls.append(url)
    return urls


@dataclass
class DetailData:
    kind: str  # active | sold | removed
    listing_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)
    sale: SaleData | None = None


def parse_detail(html: str, listing_id: str) -> DetailData:
    payload = extract_rsc(html)
    active = _richest(find_objects(payload, "ActivePropertyListing"), id=listing_id)
    if active and len(active) > 10:
        active = Rows(payload).resolve(active)
        coords = active.get("coordinates") or {}
        hf = active.get("housingForm") or {}
        municipality = active.get("municipality") or {}
        districts = [
            d["fullName"]
            for d in active.get("districts") or []
            if isinstance(d, dict) and d.get("fullName")
        ]
        fields = {
            "housing_form": hf.get("symbol"),
            "housing_form_name": hf.get("name"),
            "tenure": (active.get("tenure") or {}).get("name"),
            "street_address": active.get("streetAddress"),
            "area_name": active.get("area"),
            "municipality": municipality.get("fullName"),
            "districts": districts,
            "postcode": active.get("postCode"),
            "lat": coords.get("lat"),
            "lon": coords.get("long"),
            "asking_price": _money(active.get("askingPrice")),
            "fee": _money(active.get("fee")),
            "running_costs": _money(active.get("runningCosts")),
            "sqm_price": _money(active.get("squareMeterPrice")),
            "living_area": active.get("livingArea"),
            "supplemental_area": active.get("supplementalArea"),
            "land_area": active.get("landArea"),
            "rooms": active.get("numberOfRooms"),
            "floor": active.get("formattedFloor"),
            "year_built": parse_year(active.get("legacyConstructionYear")),
            "has_balcony": _amenity(active, "BALCONY"),
            "has_elevator": _amenity(active, "ELEVATOR"),
            "energy_class": (active.get("energyClassification") or {}).get("classification"),
            "brf_name": (active.get("brf") or {}).get("name"),
            "broker_name": (active.get("broker") or {}).get("name"),
            "broker_agency": (active.get("brokerAgency") or {}).get("name"),
            "description": active.get("description"),
            "new_construction": bool(active.get("isNewConstruction")),
            "upcoming": bool(active.get("isUpcoming")),
            "published_at": parse_ts(active.get("publishedAt")),
        }
        labels = [lb["identifier"] for lb in active.get("labels") or [] if lb.get("identifier")]
        if labels:
            fields["labels"] = labels
        fields = {k: v for k, v in fields.items() if v is not None}
        return DetailData("active", listing_id, fields, _gallery(active))

    sold = _richest(find_objects(payload, "SoldPropertyListing"), listingId=listing_id)
    if sold:
        url = sold.get("hemnetUrl") or ""
        sale = SaleData(
            sale_id=str(sold.get("id")),
            listing_id=listing_id,
            slug=url.rsplit("/", 1)[-1],
            final_price=_money(sold.get("sellingPrice")),
            final_price_text=(sold.get("sellingPrice") or {}).get("formatted"),
            asking_price=_money(sold.get("askingPrice")),
            sold_at=parse_ts(sold.get("soldAt")),
            price_change=sold.get("formattedPriceChangePercentageWithSign"),
        )
        return DetailData("sold", listing_id, sale=sale)

    if find_objects(payload, "DeactivatedPropertyListing"):
        return DetailData("removed", listing_id)
    raise ParseError(f"No listing data found on detail page for {listing_id}")


@dataclass
class Location:
    id: str
    name: str
    location_type: str
    parent_name: str | None


def parse_locations(data: list[dict[str, Any]]) -> list[Location]:
    return [
        Location(
            id=str(d["id"]),
            name=d.get("name") or "",
            location_type=d.get("location_type") or "",
            parent_name=(d.get("parent_location") or {}).get("name"),
        )
        for d in data
        if isinstance(d, dict) and d.get("id")
    ]
