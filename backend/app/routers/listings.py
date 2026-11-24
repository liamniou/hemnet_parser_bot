from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import Listing, ListingRegion, Region, User, UserListing
from app.schemas import (
    ImageOut,
    ListingDetailOut,
    ListingPage,
    ListingQuery,
    ListingStateIn,
    MapPoint,
    PriceChangeOut,
)
from app.services import browse

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.post("/query", response_model=ListingPage)
def query(q: ListingQuery, user: User = Depends(current_user), db: Session = Depends(get_db)):
    items, total = browse.query_listings(db, user.id, q)
    return ListingPage(items=items, total=total, page=q.page, page_size=q.page_size)


@router.post("/map", response_model=list[MapPoint])
def map_points(q: ListingQuery, user: User = Depends(current_user), db: Session = Depends(get_db)):
    found = browse.user_listings(db, user.id, q)
    if found is None:
        raise HTTPException(404)
    listings, _ = found
    return [
        MapPoint(
            id=x.id,
            lat=x.lat,
            lon=x.lon,
            status=x.status,
            asking_price=x.asking_price,
            street_address=x.street_address,
            rooms=x.rooms,
            living_area=x.living_area,
        )
        for x in listings[:10000]
        if x.lat is not None and x.lon is not None
    ]


@router.get("/facets")
def facets(region_ids: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = [int(x) for x in region_ids.split(",") if x.strip().isdigit()]
    return browse.facets(db, ids)


@router.get("/{listing_id}", response_model=ListingDetailOut)
def detail(listing_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(404, "Listing not found")
    state = db.get(UserListing, (user.id, listing_id))
    dropped = any((pc.new_price or 0) < (pc.old_price or 0) for pc in listing.price_changes)
    card = browse.to_card(listing, state, dropped)
    out = ListingDetailOut.model_validate(listing).model_copy(update=card.model_dump())
    if listing.images:
        out.gallery = [
            ImageOut(url=f"/media/{img['file']}", w=img.get("w"), h=img.get("h"))
            for img in listing.images
        ]
    else:
        out.gallery = [ImageOut(url=u) for u in (listing.thumbnails or [])]
    out.price_history = [PriceChangeOut.model_validate(pc) for pc in listing.price_changes]
    out.note = state.note if state else None
    out.regions = list(
        db.scalars(
            select(Region.name)
            .join(ListingRegion, ListingRegion.region_id == Region.id)
            .where(ListingRegion.listing_id == listing_id)
        )
    )
    return out


@router.put("/{listing_id}/state")
def set_state(
    listing_id: str,
    body: ListingStateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if db.get(Listing, listing_id) is None:
        raise HTTPException(404, "Listing not found")
    state = db.get(UserListing, (user.id, listing_id))
    if state is None:
        state = UserListing(user_id=user.id, listing_id=listing_id)
        db.add(state)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(state, k, v)
    db.commit()
    return {
        "favorite": state.favorite,
        "hidden": state.hidden,
        "subscribed": bool(state.subscribed),
        "note": state.note,
    }
