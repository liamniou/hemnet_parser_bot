import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.hemnet import parse
from app.hemnet.client import get_client
from app.models import JobRun, Listing, ListingRegion, PriceChange, Region, utcnow
from app.services import notifications

log = logging.getLogger(__name__)

PAGE_SIZE = 50
# Hemnet stops paginating after 50 pages: later pages are empty but still report the real total.
HEMNET_MAX_RESULTS = 2500
# Scans of overlapping regions would race on inserting the same new listing, and all
# hemnet.se requests are serialized anyway, so only one region scan runs at a time.
SCAN_LOCK = threading.Lock()
DETAIL_MAX_ATTEMPTS = 3
# Card fields that change over a listing's lifetime and are refreshed on every scan.
_VOLATILE = ("asking_price_text", "fee", "sqm_price", "upcoming", "location_description")


@dataclass
class ScanResult:
    mode: str
    pages: int = 0
    seen: int = 0
    new: int = 0
    price_changes: int = 0
    removed: int = 0
    total: int = 0
    complete: bool = False

    def __str__(self) -> str:
        return (
            f"{self.mode}: pages={self.pages} seen={self.seen}/{self.total} new={self.new} "
            f"price_changes={self.price_changes} removed={self.removed} complete={self.complete}"
        )


def _new_listing(card: parse.CardData, seed: bool, now: datetime) -> Listing:
    return Listing(
        id=card.id,
        slug=card.slug,
        record_type=card.record_type,
        housing_form=card.housing_form,
        housing_form_name=card.housing_form_name,
        street_address=card.street_address,
        location_description=card.location_description,
        lat=card.lat,
        lon=card.lon,
        asking_price=card.asking_price,
        asking_price_text=card.asking_price_text,
        fee=card.fee,
        sqm_price=card.sqm_price,
        living_area=card.living_area,
        supplemental_area=card.supplemental_area,
        land_area=card.land_area,
        rooms=card.rooms,
        floor=card.floor,
        has_balcony=card.has_balcony,
        has_elevator=card.has_elevator,
        labels=card.labels,
        new_construction=card.new_construction,
        upcoming=card.upcoming,
        published_at=card.published_at,
        broker_name=card.broker_name,
        broker_agency=card.broker_agency,
        description=card.description,
        thumbnails=card.thumbnails,
        seed=seed,
        first_seen_at=now,
        last_seen_at=now,
    )


def record_price(db: Session, listing: Listing, new_price: int | None, now: datetime) -> bool:
    """Store a price change; returns True when it is a drop worth announcing."""
    old = listing.asking_price
    if new_price is None or old is None or new_price == old:
        if new_price is not None:
            listing.asking_price = new_price
        return False
    db.add(PriceChange(listing_id=listing.id, old_price=old, new_price=new_price, changed_at=now))
    listing.asking_price = new_price
    return new_price < old


def upsert_card(
    db: Session, card: parse.CardData, region_id: int, seed: bool, now: datetime
) -> tuple[Listing, bool, bool]:
    """Returns (listing, is_new, price_dropped)."""
    listing = db.get(Listing, card.id)
    if listing is None:
        listing = _new_listing(card, seed, now)
        db.add(listing)
        db.add(ListingRegion(listing_id=card.id, region_id=region_id))
        return listing, True, False

    if db.get(ListingRegion, (card.id, region_id)) is None:
        db.add(ListingRegion(listing_id=card.id, region_id=region_id))
    if listing.status == "removed":
        listing.status, listing.removed_at, listing.status_checked_at = "active", None, None
    dropped = record_price(db, listing, card.asking_price, now)
    for attr in _VOLATILE:
        value = getattr(card, attr)
        if value is not None:
            setattr(listing, attr, value)
    if card.labels:
        listing.labels = card.labels
    if card.thumbnails:
        listing.thumbnails = card.thumbnails
    listing.slug = card.slug or listing.slug
    listing.last_seen_at = now
    return listing, False, dropped


def _start_job(job: str, region_id: int | None) -> int:
    with session_scope() as db:
        run = JobRun(job=job, region_id=region_id)
        db.add(run)
        db.flush()
        return run.id


def _finish_job(run_id: int, ok: bool, summary: str) -> None:
    with session_scope() as db:
        run = db.get(JobRun, run_id)
        run.finished_at, run.ok, run.summary = utcnow(), ok, summary[:2000]


def scan_region(region_id: int, mode: str = "auto") -> ScanResult:
    with SCAN_LOCK:
        return _scan_region(region_id, mode)


def _scan_region(region_id: int, mode: str) -> ScanResult:
    """Scrape a region's search results.

    * seed: first scan of a region - archives everything, announces nothing.
    * full: walks every page; refreshes prices and detects listings that disappeared.
    * incremental: only listings published in the last day (cheap, run frequently).
    """
    s = get_settings()
    client = get_client()
    now = utcnow()
    with session_scope() as db:
        region = db.get(Region, region_id)
        if region is None:
            raise ValueError(f"Region {region_id} not found")
        location_id, item_types, seeded = region.location_id, list(region.item_types), region.seeded
        last_full, last_scan = region.last_full_scan_at, region.last_scan_at

    if not seeded:
        mode = "seed"
    elif mode == "auto":
        stale_full = last_full is None or now - last_full > timedelta(hours=s.full_scan_hours)
        stale_scan = last_scan is None or now - last_scan > timedelta(hours=20)
        mode = "full" if stale_full or stale_scan else "incremental"

    result = ScanResult(mode=mode)
    run_id = _start_job(f"scan:{mode}", region_id)
    seen: set[str] = set()
    try:
        page = 1
        while page <= s.max_pages_per_scan:
            sp = client.search(
                location_id,
                item_types,
                page=page,
                published_since="1d" if mode == "incremental" else None,
            )
            result.pages, result.total = page, sp.total
            fresh = [c for c in sp.cards if c.id not in seen]
            if not fresh:
                result.complete = sp.total <= HEMNET_MAX_RESULTS
                break
            drops: list[str] = []
            with session_scope() as db:
                for card in fresh:
                    seen.add(card.id)
                    listing, is_new, dropped = upsert_card(db, card, region_id, mode == "seed", now)
                    result.new += is_new
                    if dropped:
                        drops.append(listing.id)
                result.price_changes += len(drops)
                db.flush()
                for lid in drops:
                    listing = db.get(Listing, lid)
                    notifications.enqueue_followup(
                        db, listing, "price_drop", ref=str(listing.asking_price)
                    )
            if len(seen) >= sp.total or len(sp.cards) < PAGE_SIZE:
                # The total can drift by a few listings during a scan; a natural last page
                # is a complete walk unless Hemnet's pagination cap cut the results short.
                result.complete = sp.total <= HEMNET_MAX_RESULTS
                break
            page += 1
        result.seen = len(seen)

        with session_scope() as db:
            region = db.get(Region, region_id)
            region.last_scan_at = now
            region.last_total = result.total if mode != "incremental" else region.last_total
            region.last_error = None
            if mode in ("seed", "full"):
                region.last_full_scan_at = now
                region.seeded = True
                if result.complete:
                    result.removed = _mark_missing(db, region_id, now)
        _finish_job(run_id, True, str(result))
        log.info("Region %s %s", region_id, result)
        return result
    except Exception as e:
        log.exception("Scan of region %s failed", region_id)
        with session_scope() as db:
            region = db.get(Region, region_id)
            first_failure = region.last_error is None
            region.last_error, region.last_error_at = f"{type(e).__name__}: {e}", utcnow()
            name = region.name
        _finish_job(run_id, False, f"{result} error={e}")
        if first_failure:
            notifications.notify_admins(f"⚠️ Hemnet scan failed for {name}: {e}")
        raise


def _mark_missing(db: Session, region_id: int, scan_started: datetime) -> int:
    """Active listings in this region not seen by a complete full scan are gone from Hemnet."""
    stale = db.scalars(
        select(Listing)
        .join(ListingRegion)
        .where(
            ListingRegion.region_id == region_id,
            Listing.status == "active",
            Listing.last_seen_at < scan_started,
        )
    )
    count = 0
    for listing in stale:
        listing.status, listing.removed_at, listing.status_checked_at = "removed", utcnow(), None
        count += 1
    return count


def apply_sale(db: Session, listing: Listing, sale: parse.SaleData) -> bool:
    if listing.status == "sold":
        return False
    listing.status = "sold"
    listing.sold_price = sale.final_price
    listing.sold_price_text = sale.final_price_text
    listing.sold_at = sale.sold_at
    listing.sold_price_change = sale.price_change
    listing.status_checked_at = utcnow()
    notifications.enqueue_followup(db, listing, "sold")
    return True


def scan_sold(region_id: int, max_pages: int = 10) -> int:
    with SCAN_LOCK:
        return _scan_sold(region_id, max_pages)


def _scan_sold(region_id: int, max_pages: int) -> int:
    client = get_client()
    with session_scope() as db:
        region = db.get(Region, region_id)
        location_id, item_types = region.location_id, list(region.item_types)
        last = region.last_sold_scan_at
    # Brokers report sales with a delay; look a month further back than the last scan.
    cutoff = (last - timedelta(days=30)) if last else utcnow() - timedelta(days=60)
    run_id = _start_job("sold", region_id)
    found = 0
    try:
        for page in range(1, max_pages + 1):
            _, sales = client.sold(location_id, item_types, page=page)
            if not sales:
                break
            with session_scope() as db:
                for sale in sales:
                    listing = db.get(Listing, sale.listing_id) if sale.listing_id else None
                    if listing is not None and apply_sale(db, listing, sale):
                        found += 1
            if all(s.sold_at and s.sold_at < cutoff for s in sales):
                break
        with session_scope() as db:
            db.get(Region, region_id).last_sold_scan_at = utcnow()
        _finish_job(run_id, True, f"sold: {found} newly sold")
        return found
    except Exception as e:
        log.exception("Sold scan of region %s failed", region_id)
        _finish_job(run_id, False, f"sold error={e}")
        raise


def _apply_detail(db: Session, listing: Listing, detail: parse.DetailData) -> list[str]:
    """Returns follow-up event kinds to emit."""
    events: list[str] = []
    now = utcnow()
    if detail.kind == "active":
        fields = dict(detail.fields)
        if record_price(db, listing, fields.pop("asking_price", None), now):
            events.append("price_drop")
        for k, v in fields.items():
            setattr(listing, k, v)
        if detail.image_urls:
            listing.image_urls = detail.image_urls
        listing.detail_fetched_at = now
    elif detail.kind == "sold" and detail.sale:
        apply_sale(db, listing, detail.sale)
        listing.detail_fetched_at = listing.detail_fetched_at or now
    elif detail.kind == "removed":
        if listing.status == "active":
            listing.status, listing.removed_at = "removed", now
        listing.status_checked_at = now
        listing.detail_fetched_at = listing.detail_fetched_at or now
    return events


def fetch_details(limit: int | None = None) -> int:
    s = get_settings()
    client = get_client()
    with session_scope() as db:
        rows = db.execute(
            select(Listing.id, Listing.slug)
            .where(
                Listing.detail_fetched_at.is_(None),
                Listing.detail_attempts < DETAIL_MAX_ATTEMPTS,
                Listing.status == "active",
            )
            .order_by(Listing.seed, Listing.first_seen_at.desc())
            .limit(limit or s.detail_batch_size)
        ).all()
    for lid, slug in rows:
        try:
            detail = client.detail(slug, lid)
        except Exception as e:
            log.warning("Detail fetch for %s failed: %s", lid, e)
            with session_scope() as db:
                db.get(Listing, lid).detail_attempts += 1
            continue
        with session_scope() as db:
            listing = db.get(Listing, lid)
            listing.detail_attempts += 1
            for kind in _apply_detail(db, listing, detail):
                db.flush()
                notifications.enqueue_followup(db, listing, kind, ref=str(listing.asking_price))
    match_new_listings()
    return len(rows)


def match_new_listings() -> int:
    """Announce listings once their details are known (or fetching them gave up)."""
    with session_scope() as db:
        listings = db.scalars(
            select(Listing).where(
                Listing.matched_at.is_(None),
                or_(
                    Listing.detail_fetched_at.is_not(None),
                    Listing.detail_attempts >= DETAIL_MAX_ATTEMPTS,
                    Listing.status != "active",
                ),
            )
        ).all()
        queued = 0
        for listing in listings:
            if not listing.seed and listing.status == "active":
                queued += notifications.enqueue_new_listing(db, listing)
            listing.matched_at = utcnow()
        return queued


def check_removed(limit: int = 20) -> int:
    """Removed listings may have been sold: their /bostad/ URL then redirects to /salda/."""
    client = get_client()
    with session_scope() as db:
        rows = db.execute(
            select(Listing.id, Listing.slug)
            .where(Listing.status == "removed", Listing.status_checked_at.is_(None))
            .order_by(Listing.removed_at.desc())
            .limit(limit)
        ).all()
    for lid, slug in rows:
        try:
            detail = client.detail(slug, lid)
        except Exception as e:
            log.warning("Removal check for %s failed: %s", lid, e)
            detail = None
        with session_scope() as db:
            listing = db.get(Listing, lid)
            if detail is not None and detail.kind == "active":
                listing.status, listing.removed_at = "active", None
                _apply_detail(db, listing, detail)
            elif detail is not None:
                _apply_detail(db, listing, detail)
            listing.status_checked_at = utcnow()
    return len(rows)


def run_due_scans() -> None:
    s = get_settings()
    now = utcnow()
    with session_scope() as db:
        regions = db.execute(
            select(Region.id, Region.last_scan_at, Region.last_sold_scan_at, Region.seeded).where(
                Region.enabled.is_(True)
            )
        ).all()
    for rid, last_scan, last_sold, seeded in regions:
        try:
            if (
                not seeded
                or last_scan is None
                or now - last_scan >= timedelta(minutes=s.scan_interval_minutes)
            ):
                scan_region(rid)
            if seeded and (
                last_sold is None or now - last_sold >= timedelta(hours=s.sold_scan_hours)
            ):
                scan_sold(rid)
        except Exception:
            continue
