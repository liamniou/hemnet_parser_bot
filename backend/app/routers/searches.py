from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import SavedSearch, User
from app.schemas import CriteriaIn, SearchIn, SearchOut
from app.services import browse

router = APIRouter(prefix="/api/searches", tags=["searches"])

MAX_SEARCHES = 20


def _get(db: Session, user: User, search_id: int) -> SavedSearch:
    s = db.get(SavedSearch, search_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "Search not found")
    return s


def _out(db: Session, s: SavedSearch) -> SearchOut:
    out = SearchOut.model_validate(s)
    out.match_count = browse.count_matches(db, s)
    return out


@router.get("", response_model=list[SearchOut])
def list_searches(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.id)
    )
    return [_out(db, s) for s in rows]


@router.post("", response_model=SearchOut, status_code=201)
def create_search(
    body: SearchIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    count = db.query(SavedSearch).filter(SavedSearch.user_id == user.id).count()
    if count >= MAX_SEARCHES:
        raise HTTPException(400, f"At most {MAX_SEARCHES} searches per user")
    s = SavedSearch(user_id=user.id, **body.model_dump())
    db.add(s)
    db.commit()
    return _out(db, s)


@router.get("/{search_id}", response_model=SearchOut)
def get_search(search_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(db, _get(db, user, search_id))


@router.put("/{search_id}", response_model=SearchOut)
def update_search(
    search_id: int,
    body: SearchIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    s = _get(db, user, search_id)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return _out(db, s)


@router.delete("/{search_id}", status_code=204)
def delete_search(
    search_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    db.delete(_get(db, user, search_id))
    db.commit()


@router.post("/preview")
def preview(body: CriteriaIn, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"count": len(browse.filter_listings(db, browse.criteria_from(body), "active"))}
