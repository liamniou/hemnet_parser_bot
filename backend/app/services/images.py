import io
import logging
import shutil
import time

from PIL import Image, ImageOps
from sqlalchemy import or_, select

from app.config import get_settings
from app.db import session_scope
from app.hemnet.client import get_image_client
from app.models import Listing

log = logging.getLogger(__name__)


def resize_to_webp(data: bytes, max_size: int, quality: int) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        im.save(out, "WEBP", quality=quality, method=4)
        return out.getvalue(), im.width, im.height


def _source_urls(listing: Listing) -> list[str]:
    if listing.image_urls:
        return list(listing.image_urls)
    # Detail page unavailable: fall back to the card thumbnails, upgraded to originals.
    return [u.replace("/itemgallery_cut/", "/original/") for u in listing.thumbnails or []]


def archive_listing_images(listing_id: str) -> str:
    s = get_settings()
    client = get_image_client()
    with session_scope() as db:
        listing = db.get(Listing, listing_id)
        if listing is None:
            return "missing"
        urls = _source_urls(listing)

    target = s.images_dir / listing_id
    target.mkdir(parents=True, exist_ok=True)
    saved: list[dict] = []
    for i, url in enumerate(urls):
        try:
            data = client.download(url)
            webp, w, h = resize_to_webp(data, s.image_max_size, s.image_quality)
        except Exception as e:
            log.warning("Image %s for %s failed: %s", url, listing_id, e)
            continue
        name = f"{i:02d}.webp"
        (target / name).write_bytes(webp)
        saved.append({"file": f"{listing_id}/{name}", "w": w, "h": h, "src": url})

    status = "done" if saved or not urls else "failed"
    if not saved:
        shutil.rmtree(target, ignore_errors=True)
    with session_scope() as db:
        listing = db.get(Listing, listing_id)
        if listing is not None:
            listing.images = saved
            listing.images_status = status
    return status


def disk_full() -> bool:
    # Images may live on another disk (e.g. an NFS mount), so measure where they are stored.
    s = get_settings()
    s.images_dir.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(s.images_dir).free < s.min_free_disk_gb * 1024**3


_usage_cache: tuple[float, int] = (0.0, 0)


def images_bytes(max_age: float = 600) -> int:
    """Total archive size; cached, since walking every file is slow on network storage."""
    global _usage_cache
    now = time.monotonic()
    if now - _usage_cache[0] > max_age or not _usage_cache[0]:
        d = get_settings().images_dir
        total = sum(f.stat().st_size for f in d.rglob("*.webp")) if d.exists() else 0
        _usage_cache = (now, total)
    return _usage_cache[1]


def archive_pending(limit: int = 5) -> int:
    s = get_settings()
    if not s.archive_images:
        return 0
    if disk_full():
        log.warning("Image archiving paused: less than %s GB free", s.min_free_disk_gb)
        return 0
    with session_scope() as db:
        q = (
            select(Listing.id)
            .where(
                Listing.images_status == "pending",
                or_(Listing.detail_fetched_at.is_not(None), Listing.detail_attempts >= 3),
            )
            .order_by(Listing.seed, Listing.first_seen_at.desc())
            .limit(limit)
        )
        if not s.archive_seed_images:
            q = q.where(Listing.seed.is_(False))
        ids = list(db.scalars(q))
    for lid in ids:
        archive_listing_images(lid)
    return len(ids)


def delete_listing_images(listing_id: str) -> None:
    shutil.rmtree(get_settings().images_dir / listing_id, ignore_errors=True)
