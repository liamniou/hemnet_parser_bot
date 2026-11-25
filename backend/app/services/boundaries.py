"""Area borders for the map.

Outlines come from Hemnet itself (the same polygons hemnet.se draws when you search an area).
Regions carry their Hemnet location id; district names from listings are resolved to an id via
Hemnet's location search. If Hemnet has no outline, an approximate one is drawn around the
area's listings instead.
"""

import logging
import math
import unicodedata
from datetime import timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.hemnet.client import get_client
from app.models import Boundary, Listing, ListingRegion, Region, utcnow
from app.services.matching import listing_places

log = logging.getLogger(__name__)

FOUND_TTL = timedelta(days=90)
MISSING_TTL = timedelta(days=7)


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFC", s or "").casefold().strip()


def to_geojson(polygons: list) -> dict | None:
    valid = [
        p
        for p in polygons
        if isinstance(p, list)
        and p
        and all(isinstance(ring, list) and len(ring) >= 4 for ring in p)
    ]
    if not valid:
        return None
    if len(valid) == 1:
        return {"type": "Polygon", "coordinates": valid[0]}
    return {"type": "MultiPolygon", "coordinates": valid}


def _fresh(row: Boundary | None) -> bool:
    if row is None:
        return False
    return utcnow() - row.fetched_at < (FOUND_TTL if row.geojson else MISSING_TTL)


def _save(db: Session, key: str, name: str, context: str | None, geojson, label) -> Boundary:
    row = db.get(Boundary, key) or Boundary(key=key)
    row.name, row.context, row.geojson, row.label = name, context, geojson, label
    row.fetched_at = utcnow()
    db.merge(row)
    db.commit()
    return row


def location_outline(db: Session, location_id: str, name: str) -> Boundary:
    """Cached Hemnet outline for a location id."""
    key = f"hemnet:{location_id}"
    cached = db.get(Boundary, key)
    if _fresh(cached):
        return cached
    try:
        geojson = to_geojson(get_client().location_polygons(location_id))
    except Exception as e:
        log.warning("Hemnet outline for location %s failed: %s", location_id, e)
        return cached or Boundary(key=key, name=name, geojson=None)
    return _save(db, key, name, None, geojson, f"{location_id}:{name}")


def pick_location(locations, name: str, context: str | None):
    """The Hemnet location called exactly `name`, preferably inside municipality `context`."""
    exact = [x for x in locations if _norm(x.name) == _norm(name)]
    if context:
        local = [x for x in exact if _norm(x.parent_name) == _norm(context)]
        exact = local or (exact if len(exact) == 1 else [])
    exact.sort(key=lambda x: x.location_type != "district")
    return exact[0] if exact else None


def district_outline(db: Session, name: str, context: str | None) -> Boundary:
    key = f"hemnet-district:{_norm(name)}|{_norm(context)}"
    cached = db.get(Boundary, key)
    if _fresh(cached):
        return cached
    client = get_client()
    try:
        locs = [pick_location(client.locations(name), name, context)]
        # Listings use combined labels ("Kista / Hässelby / Vällingby / Spånga") that Hemnet's
        # location search doesn't know; then outline every part, but only if all parts exist.
        parts = [p.strip() for p in name.split(" / ") if p.strip()]
        if locs[0] is None and len(parts) > 1:
            locs = []
            for part in parts:
                locs.append(pick_location(client.locations(part), part, context))
                if locs[-1] is None:
                    break
        if not locs or None in locs:
            geojson, label = None, None
        else:
            polygons = [p for loc in locs for p in client.location_polygons(loc.id)]
            geojson = to_geojson(polygons)
            label = ", ".join(f"{loc.id}:{loc.name}" for loc in locs)
    except Exception as e:
        log.warning("Hemnet outline for district %r failed: %s", name, e)
        return cached or Boundary(key=key, name=name, context=context, geojson=None)
    return _save(db, key, name, context, geojson, label)


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


def _municipality(listing) -> str | None:
    if listing.municipality:
        return listing.municipality
    tail = (listing.location_description or "").rsplit(",", 1)[-1].strip()
    return tail if tail.endswith(" kommun") else None


def district_boundary(db: Session, name: str) -> dict:
    cols = (
        Listing.lat,
        Listing.lon,
        Listing.districts,
        Listing.area_name,
        Listing.location_description,
        Listing.municipality,
    )
    # Plain rows instead of ORM objects: this scans every listing on each call.
    rows = db.execute(select(*cols).where(Listing.lat.is_not(None)))
    listings = [x for x in rows if name in listing_places(x)]
    municipalities = [m for m in map(_municipality, listings) if m]
    context = max(set(municipalities), key=municipalities.count) if municipalities else None
    found = district_outline(db, name, context)
    if found.geojson:
        return _result("district", name, name, found.geojson, "hemnet")
    hull = hull_outline([(x.lon, x.lat) for x in listings])
    return _result(
        "district", name, name, hull, "listings" if hull else None, listing_count=len(listings)
    )


def region_boundary(db: Session, region: Region) -> dict:
    found = location_outline(db, region.location_id, region.name)
    if found.geojson:
        return _result("region", str(region.id), region.name, found.geojson, "hemnet")
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


def location_preview(location_id: str, name: str) -> dict:
    """Border for a Hemnet location that isn't a region yet (admin preview)."""
    with session_scope() as db:
        found = location_outline(db, location_id, name)
        geojson = found.geojson
        return _result("location", location_id, name, geojson, "hemnet" if geojson else None)
