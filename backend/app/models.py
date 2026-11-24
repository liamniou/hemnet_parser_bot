from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    # Never reuse ids of deleted users: sessions reference them.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    searches: Mapped[list["SavedSearch"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.name or self.email


class LoginRequest(Base):
    """An emailed sign-in: a 6-digit code (stored hashed) plus a link token."""

    __tablename__ = "login_requests"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    location_type: Mapped[str | None] = mapped_column(String(32))
    parent_name: Mapped[str | None] = mapped_column(String(255))
    item_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    seeded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_full_scan_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_sold_scan_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_total: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("location_id", name="uq_region_location"),)


class ListingRegion(Base):
    __tablename__ = "listing_regions"

    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    slug: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    record_type: Mapped[str | None] = mapped_column(String(32))

    housing_form: Mapped[str | None] = mapped_column(String(32), index=True)
    housing_form_name: Mapped[str | None] = mapped_column(String(64))
    tenure: Mapped[str | None] = mapped_column(String(64))
    street_address: Mapped[str | None] = mapped_column(String(255))
    location_description: Mapped[str | None] = mapped_column(String(255))
    area_name: Mapped[str | None] = mapped_column(String(255))
    municipality: Mapped[str | None] = mapped_column(String(255))
    districts: Mapped[list[str]] = mapped_column(JSON, default=list)
    postcode: Mapped[str | None] = mapped_column(String(16))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)

    asking_price: Mapped[int | None] = mapped_column(Integer, index=True)
    asking_price_text: Mapped[str | None] = mapped_column(String(64))
    fee: Mapped[int | None] = mapped_column(Integer)
    running_costs: Mapped[int | None] = mapped_column(Integer)
    sqm_price: Mapped[int | None] = mapped_column(Integer)
    living_area: Mapped[float | None] = mapped_column(Float)
    supplemental_area: Mapped[float | None] = mapped_column(Float)
    land_area: Mapped[float | None] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float)
    floor: Mapped[str | None] = mapped_column(String(64))
    year_built: Mapped[int | None] = mapped_column(Integer)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean)
    has_elevator: Mapped[bool | None] = mapped_column(Boolean)
    energy_class: Mapped[str | None] = mapped_column(String(8))
    brf_name: Mapped[str | None] = mapped_column(String(255))
    broker_name: Mapped[str | None] = mapped_column(String(255))
    broker_agency: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    new_construction: Mapped[bool] = mapped_column(Boolean, default=False)
    upcoming: Mapped[bool] = mapped_column(Boolean, default=False)
    thumbnails: Mapped[list[str]] = mapped_column(JSON, default=list)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    images: Mapped[list[dict]] = mapped_column(JSON, default=list)

    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Listings found during a region's initial seed are archived but never announced.
    seed: Mapped[bool] = mapped_column(Boolean, default=False)
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    detail_attempts: Mapped[int] = mapped_column(Integer, default=0)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime)
    images_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    sold_price: Mapped[int | None] = mapped_column(Integer)
    sold_price_text: Mapped[str | None] = mapped_column(String(64))
    sold_at: Mapped[datetime | None] = mapped_column(DateTime)
    sold_price_change: Mapped[str | None] = mapped_column(String(32))

    price_changes: Mapped[list["PriceChange"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="PriceChange.changed_at"
    )

    @property
    def url(self) -> str:
        return f"https://www.hemnet.se/bostad/{self.slug}"


class PriceChange(Base):
    __tablename__ = "price_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    old_price: Mapped[int | None] = mapped_column(Integer)
    new_price: Mapped[int | None] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listing: Mapped[Listing] = relationship(back_populates="price_changes")


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    region_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    districts: Mapped[list[str]] = mapped_column(JSON, default=list)
    housing_forms: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_min: Mapped[int | None] = mapped_column(Integer)
    price_max: Mapped[int | None] = mapped_column(Integer)
    rooms_min: Mapped[float | None] = mapped_column(Float)
    rooms_max: Mapped[float | None] = mapped_column(Float)
    living_area_min: Mapped[float | None] = mapped_column(Float)
    living_area_max: Mapped[float | None] = mapped_column(Float)
    fee_max: Mapped[int | None] = mapped_column(Integer)
    sqm_price_max: Mapped[int | None] = mapped_column(Integer)
    year_built_min: Mapped[int | None] = mapped_column(Integer)
    year_built_max: Mapped[int | None] = mapped_column(Integer)
    require_balcony: Mapped[bool] = mapped_column(Boolean, default=False)
    require_elevator: Mapped[bool] = mapped_column(Boolean, default=False)
    include_new_construction: Mapped[bool] = mapped_column(Boolean, default=False)
    keywords: Mapped[str | None] = mapped_column(String(512))
    center_lat: Mapped[float | None] = mapped_column(Float)
    center_lon: Mapped[float | None] = mapped_column(Float)
    radius_km: Mapped[float | None] = mapped_column(Float)

    notify_new: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_price_drop: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_sold: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="searches")


class UserListing(Base):
    __tablename__ = "user_listings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[str | None] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    search_id: Mapped[int | None] = mapped_column(
        ForeignKey("saved_searches.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16))  # new | price_drop | sold | test
    channel: Mapped[str] = mapped_column(String(16), default="email")
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    listing: Mapped[Listing | None] = relationship()
    search: Mapped[SavedSearch | None] = relationship()


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    ok: Mapped[bool | None] = mapped_column(Boolean)
    summary: Mapped[str | None] = mapped_column(Text)
