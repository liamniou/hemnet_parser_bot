import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, fields

from app.models import Listing, SavedSearch


@dataclass
class Criteria:
    """Listing filter shared by saved searches (notifications) and the browse UI."""

    region_ids: list[int] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    housing_forms: list[str] = field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None
    rooms_min: float | None = None
    rooms_max: float | None = None
    living_area_min: float | None = None
    living_area_max: float | None = None
    fee_max: int | None = None
    sqm_price_max: int | None = None
    year_built_min: int | None = None
    year_built_max: int | None = None
    require_balcony: bool = False
    require_elevator: bool = False
    include_new_construction: bool = True
    keywords: str | None = None
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float | None = None
    water_distance_max: int | None = None

    @classmethod
    def from_search(cls, s: SavedSearch) -> "Criteria":
        return cls(**{f.name: getattr(s, f.name) for f in fields(cls)})


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _in_range(value: float | None, lo: float | None, hi: float | None, strict: bool) -> bool:
    if lo is None and hi is None:
        return True
    if value is None:
        return not strict
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def parse_keywords(text: str | None) -> tuple[list[str], list[str]]:
    include, exclude = [], []
    for raw in re.split(r"[,\n]", text or ""):
        kw = raw.strip().casefold()
        if not kw:
            continue
        if kw.startswith("-") and len(kw) > 1:
            exclude.append(kw[1:].strip())
        else:
            include.append(kw)
    return include, exclude


def listing_places(listing: Listing) -> set[str]:
    places = set(listing.districts or [])
    if listing.area_name:
        places.add(listing.area_name)
    if listing.location_description:
        places.add(listing.location_description.split(",")[0].strip())
    return {p for p in places if p}


def matches(c: Criteria, listing: Listing, region_ids: Iterable[int]) -> bool:
    if c.region_ids and not set(c.region_ids) & set(region_ids):
        return False
    if c.districts and not listing_places(listing) & set(c.districts):
        return False
    if c.housing_forms and listing.housing_form not in c.housing_forms:
        return False
    if not c.include_new_construction and listing.new_construction:
        return False
    # Core size/price constraints are strict: unknown values do not match.
    if not _in_range(listing.asking_price, c.price_min, c.price_max, strict=True):
        return False
    if not _in_range(listing.rooms, c.rooms_min, c.rooms_max, strict=True):
        return False
    if not _in_range(listing.living_area, c.living_area_min, c.living_area_max, strict=True):
        return False
    # Fee/sqm price/year are often missing (villas have no fee): unknown passes.
    if not _in_range(listing.fee, None, c.fee_max, strict=False):
        return False
    if not _in_range(listing.sqm_price, None, c.sqm_price_max, strict=False):
        return False
    if not _in_range(listing.year_built, c.year_built_min, c.year_built_max, strict=False):
        return False
    if c.require_balcony and not (listing.has_balcony or "BALCONY" in (listing.labels or [])):
        return False
    if c.require_elevator and not (listing.has_elevator or "ELEVATOR" in (listing.labels or [])):
        return False
    if c.keywords:
        include, exclude = parse_keywords(c.keywords)
        hay = " ".join(
            x
            for x in (
                listing.street_address,
                listing.location_description,
                listing.description,
                " ".join(listing.districts or []),
            )
            if x
        ).casefold()
        if include and not any(k in hay for k in include):
            return False
        if any(k in hay for k in exclude):
            return False
    # Unknown distance doesn't match: the user explicitly wants to be close to water.
    if not _in_range(listing.water_distance, None, c.water_distance_max, strict=True):
        return False
    if c.radius_km and c.center_lat is not None and c.center_lon is not None:
        if listing.lat is None or listing.lon is None:
            return False
        if haversine_km(c.center_lat, c.center_lon, listing.lat, listing.lon) > c.radius_km:
            return False
    return True
