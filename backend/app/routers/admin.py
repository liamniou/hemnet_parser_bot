import shutil
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import admin_user
from app.config import get_settings
from app.db import get_db
from app.hemnet.client import ITEM_TYPES, get_client
from app.models import (
    JobRun,
    Listing,
    ListingRegion,
    Notification,
    Region,
    SavedSearch,
    User,
)
from app.schemas import (
    AdminUserOut,
    AdminUserUpdate,
    JobRunOut,
    RegionAdminOut,
    RegionIn,
    RegionUpdate,
)
from app.services import scanner
from app.services.boundaries import location_preview
from app.services.images import images_bytes

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/item-types")
def item_types():
    return [{"value": k, "label": v} for k, v in ITEM_TYPES.items()]


@router.get("/locations")
def locations(q: str):
    if len(q.strip()) < 2:
        return []
    try:
        return [loc.__dict__ for loc in get_client().locations(q.strip())]
    except Exception as e:
        raise HTTPException(502, f"Hemnet lookup failed: {e}") from e


@router.get("/boundary-preview")
def boundary_preview(location_id: str, name: str = ""):
    return location_preview(location_id, name)


def _region_out(db: Session, r: Region) -> RegionAdminOut:
    out = RegionAdminOut.model_validate(r)
    counts = dict(
        db.execute(
            select(Listing.status, func.count())
            .join(ListingRegion, ListingRegion.listing_id == Listing.id)
            .where(ListingRegion.region_id == r.id)
            .group_by(Listing.status)
        ).all()
    )
    out.listing_count = sum(counts.values())
    out.active_count = counts.get("active", 0)
    return out


@router.get("/regions", response_model=list[RegionAdminOut])
def list_regions(db: Session = Depends(get_db)):
    return [_region_out(db, r) for r in db.scalars(select(Region).order_by(Region.name))]


def _validate_types(types: list[str]) -> list[str]:
    bad = [t for t in types if t not in ITEM_TYPES]
    if bad:
        raise HTTPException(400, f"Unknown item types: {', '.join(bad)}")
    return sorted(set(types))


@router.post("/regions", response_model=RegionAdminOut, status_code=201)
def create_region(body: RegionIn, db: Session = Depends(get_db)):
    if db.scalar(select(Region).where(Region.location_id == body.location_id)):
        raise HTTPException(409, "Region already exists")
    data = body.model_dump()
    data["item_types"] = _validate_types(body.item_types)
    r = Region(**data)
    db.add(r)
    db.commit()
    if r.enabled:
        _start_scan(r.id, "auto")
    return _region_out(db, r)


@router.patch("/regions/{region_id}", response_model=RegionAdminOut)
def update_region(region_id: int, body: RegionUpdate, db: Session = Depends(get_db)):
    r = db.get(Region, region_id)
    if r is None:
        raise HTTPException(404)
    if body.item_types is not None:
        types = _validate_types(body.item_types)
        if types != sorted(r.item_types or []):
            r.item_types = types
            # Re-seed so listings of newly added types are archived, not announced as new.
            r.seeded = False
    if body.enabled is not None:
        r.enabled = body.enabled
    db.commit()
    return _region_out(db, r)


@router.delete("/regions/{region_id}", status_code=204)
def delete_region(region_id: int, purge: bool = False, db: Session = Depends(get_db)):
    r = db.get(Region, region_id)
    if r is None:
        raise HTTPException(404)
    if purge:
        # Delete listings that belong only to this region (and their archived images).
        from app.services.images import delete_listing_images

        only_here = db.scalars(
            select(ListingRegion.listing_id)
            .group_by(ListingRegion.listing_id)
            .having(func.count() == 1, func.max(ListingRegion.region_id) == region_id)
        ).all()
        for lid in only_here:
            delete_listing_images(lid)
            db.delete(db.get(Listing, lid))
    db.delete(r)
    db.commit()


_running: set[int] = set()


def _start_scan(region_id: int, mode: str) -> bool:
    if region_id in _running:
        return False
    _running.add(region_id)

    def run():
        try:
            if mode == "sold":
                scanner.scan_sold(region_id)
            else:
                scanner.scan_region(region_id, mode)
        except Exception:
            pass
        finally:
            _running.discard(region_id)

    threading.Thread(target=run, daemon=True).start()
    return True


@router.post("/regions/{region_id}/scan", status_code=202)
def trigger_scan(region_id: int, mode: str = "auto", db: Session = Depends(get_db)):
    if db.get(Region, region_id) is None:
        raise HTTPException(404)
    if mode not in ("auto", "full", "incremental", "sold"):
        raise HTTPException(400, "Invalid mode")
    if not _start_scan(region_id, mode):
        raise HTTPException(409, "Scan already running")
    return {"started": True}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    s = get_settings()
    by_status = dict(
        db.execute(select(Listing.status, func.count()).group_by(Listing.status)).all()
    )
    images = dict(
        db.execute(
            select(Listing.images_status, func.count()).group_by(Listing.images_status)
        ).all()
    )
    pending_details = db.scalar(
        select(func.count()).where(
            Listing.detail_fetched_at.is_(None),
            Listing.detail_attempts < scanner.DETAIL_MAX_ATTEMPTS,
            Listing.status == "active",
        )
    )
    notif = dict(
        db.execute(select(Notification.status, func.count()).group_by(Notification.status)).all()
    )
    img_bytes = images_bytes()
    disk = shutil.disk_usage(s.images_dir) if s.images_dir.exists() else None
    return {
        "listings": by_status,
        "images": images,
        "pending_details": pending_details,
        "notifications": notif,
        "users": db.scalar(select(func.count()).select_from(User)),
        "searches": db.scalar(select(func.count()).select_from(SavedSearch)),
        "images_bytes": img_bytes,
        "db_bytes": sum(
            p.stat().st_size for p in s.data_dir.glob(f"{s.db_path.name}*") if p.is_file()
        ),
        "disk_free_bytes": disk.free if disk else None,
        "running_scans": sorted(_running),
        "settings": {
            "scan_interval_minutes": s.scan_interval_minutes,
            "full_scan_hours": s.full_scan_hours,
            "sold_scan_hours": s.sold_scan_hours,
            "max_pages_per_scan": s.max_pages_per_scan,
            "archive_images": s.archive_images,
            "archive_seed_images": s.archive_seed_images,
            "image_max_size": s.image_max_size,
            "min_free_disk_gb": s.min_free_disk_gb,
            "smtp": s.smtp_enabled,
        },
    }


@router.get("/jobs", response_model=list[JobRunOut])
def jobs(limit: int = 50, db: Session = Depends(get_db)):
    return db.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(min(limit, 500))).all()


@router.get("/users", response_model=list[AdminUserOut])
def users(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(select(SavedSearch.user_id, func.count()).group_by(SavedSearch.user_id)).all()
    )
    out = []
    for u in db.scalars(select(User).order_by(User.id)):
        item = AdminUserOut.model_validate(u)
        item.search_count = counts.get(u.id, 0)
        out.append(item)
    return out


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(admin_user),
):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404)
    if u.id == me.id and (body.is_admin is False or body.disabled):
        raise HTTPException(400, "You cannot demote or disable yourself")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(u, k, v)
    db.commit()
    return AdminUserOut.model_validate(u)
