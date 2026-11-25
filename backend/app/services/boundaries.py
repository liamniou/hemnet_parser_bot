"""Area borders for the map.

Real borders come from OpenStreetMap (Nominatim) when a place with a matching name exists.
Hemnet's own areas often don't exist in OSM (e.g. "Vasastan / Norrmalm"), so those fall back to
an approximate outline: the convex hull around listings in the area.
"""

import logging
import math
import threading
import time
import unicodedata
from datetime import timedelta
from statistics import median
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import Boundary, Listing, ListingRegion, Region, utcnow
from app.services.matching import listing_places

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Only real places/administrative areas count; never shops, schools or streets with that name.
PLACE_TYPES = {
    "suburb", "quarter", "neighbourhood", "city_district", "borough", "district",
    "municipality", "town", "village", "hamlet", "city", "island", "county", "state_district",
}  # fmt: skip
FOUND_TTL = timedelta(days=90)
MISSING_TTL = timedelta(days=14)

_lock = threading.Lock()
_last_call = 0.0


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFC", s or "").casefold().strip()
    return s.removesuffix(" kommun").strip()


def name_matches(wanted: str, osm_name: str | None) -> bool:
    """Same place name, tolerating Swedish endings (Vasastan ~ Vasastaden)."""
    a, b = _norm(wanted), _norm(osm_name)
    if not a or not b:
        return False
    if a == b:
        return True
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    return p >= 6 and abs(len(a) - len(b)) <= 4


def _nominatim_search(query: str) -> list[dict[str, Any]]:
    """One Nominatim query, at most one per second as its usage policy requires."""
    global _last_call
    s = get_settings()
    contact = s.smtp_from or s.public_url
    with _lock:
        wait = _last_call + 1.1 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(
                NOMINATIM,
                params={
                    "q": query,
                    "countrycodes": "se",
                    "format": "jsonv2",
                    "polygon_geojson": 1,
                    "polygon_threshold": 0.0003,
                    "limit": 8,
                },
                headers={"User-Agent": f"HemnetWatch/1.0 (self-hosted; {contact})"},
                timeout=20,
            )
            r.raise_for_status()
            return r.json()
        finally:
            _last_call = time.monotonic()


def osm_boundary(db: Session, name: str, context: str | None) -> Boundary:
    """Cached OSM lookup of `name` near `context` (municipality or county)."""
    key = f"{_norm(name)}|{_norm(context)}"
    cached = db.get(Boundary, key)
    if cached:
        ttl = FOUND_TTL if cached.geojson else MISSING_TTL
        if utcnow() - cached.fetched_at < ttl:
            return cached
    query = f"{name}, {context}" if context else name
    try:
        results = _nominatim_search(query)
    except Exception as e:
        log.warning("Nominatim lookup for %r failed: %s", query, e)
        if cached:
            return cached
        return Boundary(key=key, name=name, context=context, geojson=None, fetched_at=utcnow())
    best = next(
        (
            r
            for r in results
            if (r.get("geojson") or {}).get("type") in ("Polygon", "MultiPolygon")
            and r.get("category") in ("boundary", "place")
            and (r.get("addresstype") in PLACE_TYPES or r.get("category") == "boundary")
            and name_matches(name, r.get("name"))
        ),
        None,
    )
    row = cached or Boundary(key=key)
    row.name, row.context, row.fetched_at = name, context, utcnow()
    row.geojson = best["geojson"] if best else None
    row.osm_name = best.get("display_name") if best else None
    db.merge(row)
    db.commit()
    return row


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def hull_outline(coords: list[tuple[float, float]]) -> dict | None:
    """Approximate outline around (lon, lat) points, ignoring far-off mis-geocoded ones."""
    if len(coords) < 3:
        return None
    clon, clat = median(c[0] for c in coords), median(c[1] for c in coords)
    kx = math.cos(math.radians(clat))

    def dist(c):
        return math.hypot((c[0] - clon) * kx, c[1] - clat)

    typical = median(dist(c) for c in coords)
    limit = max(3 * typical, 0.004)  # at least ~400 m
    kept = [c for c in coords if dist(c) <= limit]
    hull = _convex_hull(kept)
    if len(hull) < 3:
        return None
    # Pad outward ~80 m so listings on the edge sit inside the line.
    cx = sum(p[0] for p in hull) / len(hull)
    cy = sum(p[1] for p in hull) / len(hull)
    ring = []
    for x, y in hull:
        dx, dy = (x - cx) * kx, y - cy
        d = math.hypot(dx, dy) or 1
        ring.append([round(x + 0.0008 * dx / d / kx, 6), round(y + 0.0008 * dy / d, 6)])
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _result(kind: str, key: str, name: str, geojson: dict | None, source: str | None, **extra):
    return {"kind": kind, "key": key, "name": name, "geojson": geojson, "source": source, **extra}


def district_boundary(db: Session, name: str) -> dict:
    listings = [
        x
        for x in db.scalars(select(Listing).where(Listing.lat.is_not(None)))
        if name in listing_places(x)
    ]
    municipalities = [x.municipality for x in listings if x.municipality]
    context = max(set(municipalities), key=municipalities.count) if municipalities else None
    osm = osm_boundary(db, name, context)
    if osm.geojson:
        return _result("district", name, name, osm.geojson, "osm", label=osm.osm_name)
    hull = hull_outline([(x.lon, x.lat) for x in listings])
    return _result(
        "district", name, name, hull, "listings" if hull else None, listing_count=len(listings)
    )


def region_boundary(db: Session, region: Region) -> dict:
    osm = osm_boundary(db, region.name, region.parent_name)
    if osm.geojson:
        return _result(
            "region", str(region.id), region.name, osm.geojson, "osm", label=osm.osm_name
        )
    coords = [
        (lon, lat)
        for lon, lat in db.execute(
            select(Listing.lon, Listing.lat)
            .join(ListingRegion, ListingRegion.listing_id == Listing.id)
            .where(ListingRegion.region_id == region.id, Listing.lat.is_not(None))
        )
    ]
    hull = hull_outline(coords)
    return _result(
        "region",
        str(region.id),
        region.name,
        hull,
        "listings" if hull else None,
        listing_count=len(coords),
    )


def location_preview(name: str, parent: str | None) -> dict:
    """Border for a Hemnet location that isn't a region yet (admin preview)."""
    with session_scope() as db:
        osm = osm_boundary(db, name, parent)
        return _result(
            "location", name, name, osm.geojson, "osm" if osm.geojson else None, label=osm.osm_name
        )
