from collections import Counter
from dataclasses import fields

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Listing, ListingRegion, PriceChange, SavedSearch, UserListing
from app.schemas import CriteriaIn, ListingCardOut, ListingQuery
from app.services.matching import Criteria, matches

_SORTS = {
    "newest": lambda x: (x.published_at or x.first_seen_at).timestamp() * -1,
    "price_asc": lambda x: x.asking_price if x.asking_price is not None else float("inf"),
    "price_desc": lambda x: -(x.asking_price or 0),
    "sqm_price_asc": lambda x: x.sqm_price if x.sqm_price is not None else float("inf"),
    "area_desc": lambda x: -(x.living_area or 0),
    "sold_recent": lambda x: -(x.sold_at.timestamp() if x.sold_at else 0),
}


def criteria_from(body: CriteriaIn) -> Criteria:
    return Criteria(**{f.name: getattr(body, f.name) for f in fields(Criteria)})


def _region_map(db: Session, listing_ids: list[str] | None = None) -> dict[str, set[int]]:
    q = select(ListingRegion.listing_id, ListingRegion.region_id)
    if listing_ids is not None:
        q = q.where(ListingRegion.listing_id.in_(listing_ids))
    out: dict[str, set[int]] = {}
    for lid, rid in db.execute(q):
        out.setdefault(lid, set()).add(rid)
    return out


def filter_listings(
    db: Session, crit: Criteria, status: str = "active", text: str | None = None
) -> list[Listing]:
    q = select(Listing)
    if status != "all":
        q = q.where(Listing.status == status)
    if crit.region_ids:
        q = q.where(
            Listing.id.in_(
                select(ListingRegion.listing_id).where(ListingRegion.region_id.in_(crit.region_ids))
            )
        )
    candidates = list(db.scalars(q))
    regions = _region_map(db)
    needle = text.casefold().strip() if text else None
    out = []
    for listing in candidates:
        if not matches(crit, listing, regions.get(listing.id, set())):
            continue
        if needle:
            hay = " ".join(
                x for x in (listing.street_address, listing.location_description, listing.id) if x
            ).casefold()
            if needle not in hay:
                continue
        out.append(listing)
    return out


def card_photos(listing: Listing) -> list[str]:
    """Photos for the card slider: the archive if we have it, else Hemnet's card-sized images."""
    if listing.images:
        return [f"/media/{img['file']}" for img in listing.images]
    if listing.image_urls:
        # Gallery originals are ~2048px; the "itemgallery_cut" size of the same file is ~690px.
        return [
            u.replace("/images/original/", "/images/itemgallery_cut/") for u in listing.image_urls
        ]
    return list(listing.thumbnails or [])


def to_card(listing: Listing, state: UserListing | None, dropped: bool) -> ListingCardOut:
    card = ListingCardOut.model_validate(listing)
    card.photos = card_photos(listing)
    card.cover = card.photos[0] if card.photos else None
    card.image_count = len(listing.images or listing.image_urls or listing.thumbnails or [])
    card.price_dropped = dropped
    if state:
        card.favorite, card.hidden = state.favorite, state.hidden
        card.subscribed = bool(state.subscribed)
    return card


def user_listings(
    db: Session, user_id: int, q: ListingQuery
) -> tuple[list[Listing], dict[str, UserListing]] | None:
    """Listings matching the query, filtered by this user's saved/hidden state.

    Returns None when the query references someone else's (or a missing) saved search.
    """
    if q.search_id:
        search = db.get(SavedSearch, q.search_id)
        if search is None or search.user_id != user_id:
            return None
        crit = Criteria.from_search(search)
    else:
        crit = criteria_from(q)
    listings = filter_listings(db, crit, q.status, q.text)

    states = {
        s.listing_id: s
        for s in db.scalars(select(UserListing).where(UserListing.user_id == user_id))
    }

    def hidden(x: Listing) -> bool:
        return bool((st := states.get(x.id)) and st.hidden)

    if q.favorites_only:
        listings = [x for x in listings if (st := states.get(x.id)) and st.favorite]
    if q.subscribed_only:
        listings = [x for x in listings if (st := states.get(x.id)) and st.subscribed]
    if q.hidden_only:
        listings = [x for x in listings if hidden(x)]
    elif not q.show_hidden:
        listings = [x for x in listings if not hidden(x)]
    return listings, states


def query_listings(db: Session, user_id: int, q: ListingQuery) -> tuple[list[ListingCardOut], int]:
    found = user_listings(db, user_id, q)
    if found is None:
        return [], 0
    listings, states = found

    listings.sort(key=_SORTS.get(q.sort, _SORTS["newest"]))
    total = len(listings)
    start = (q.page - 1) * q.page_size
    page = listings[start : start + q.page_size]
    ids = [x.id for x in page]
    dropped = set(
        db.scalars(
            select(PriceChange.listing_id).where(
                PriceChange.listing_id.in_(ids), PriceChange.new_price < PriceChange.old_price
            )
        )
    )
    return [to_card(x, states.get(x.id), x.id in dropped) for x in page], total


def count_matches(db: Session, search: SavedSearch) -> int:
    return len(filter_listings(db, Criteria.from_search(search), "active"))


def facets(db: Session, region_ids: list[int]) -> dict:
    q = select(Listing).where(Listing.status == "active")
    if region_ids:
        q = q.where(
            Listing.id.in_(
                select(ListingRegion.listing_id).where(ListingRegion.region_id.in_(region_ids))
            )
        )
    places: Counter[str] = Counter()
    forms: dict[str, str] = {}
    form_counts: Counter[str] = Counter()
    lats: list[float] = []
    lons: list[float] = []
    for listing in db.scalars(q):
        if listing.lat is not None and listing.lon is not None:
            lats.append(listing.lat)
            lons.append(listing.lon)
        # Hemnet's canonical districts (from the detail page) beat the brokers' free-text
        # location, which only serves as a fallback until the detail page has been fetched.
        if listing.districts:
            places.update(listing.districts)
        elif listing.location_description:
            places[listing.location_description.split(",")[0].strip()] += 1
        if listing.housing_form:
            forms[listing.housing_form] = listing.housing_form_name or listing.housing_form
            form_counts[listing.housing_form] += 1
    return {
        "districts": [{"name": n, "count": c} for n, c in sorted(places.items())],
        "housing_forms": [
            {"symbol": s, "name": forms[s], "count": c} for s, c in form_counts.most_common()
        ],
        "center": [sorted(lats)[len(lats) // 2], sorted(lons)[len(lons) // 2]] if lats else None,
    }
