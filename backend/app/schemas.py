from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    display_name: str
    is_admin: bool
    email: str | None
    email_verified: bool
    notify_telegram: bool
    notify_email: bool
    telegram_blocked: bool
    created_at: datetime


class UserUpdate(BaseModel):
    notify_telegram: bool | None = None
    notify_email: bool | None = None


class EmailIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)


class CodeIn(BaseModel):
    code: str


class CriteriaIn(BaseModel):
    region_ids: list[int] = []
    districts: list[str] = []
    housing_forms: list[str] = []
    price_min: int | None = Field(None, ge=0)
    price_max: int | None = Field(None, ge=0)
    rooms_min: float | None = Field(None, ge=0)
    rooms_max: float | None = Field(None, ge=0)
    living_area_min: float | None = Field(None, ge=0)
    living_area_max: float | None = Field(None, ge=0)
    fee_max: int | None = Field(None, ge=0)
    sqm_price_max: int | None = Field(None, ge=0)
    year_built_min: int | None = None
    year_built_max: int | None = None
    require_balcony: bool = False
    require_elevator: bool = False
    include_new_construction: bool = True
    keywords: str | None = Field(None, max_length=512)
    center_lat: float | None = Field(None, ge=-90, le=90)
    center_lon: float | None = Field(None, ge=-180, le=180)
    radius_km: float | None = Field(None, gt=0, le=200)


class SearchIn(CriteriaIn):
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    include_new_construction: bool = False
    notify_new: bool = True
    notify_price_drop: bool = True
    notify_sold: bool = True


class SearchOut(SearchIn, ORM):
    id: int
    created_at: datetime
    updated_at: datetime
    match_count: int | None = None


class ListingQuery(CriteriaIn):
    status: str = "active"  # active | sold | removed | all
    search_id: int | None = None
    favorites_only: bool = False
    show_hidden: bool = False
    text: str | None = None
    sort: str = (
        "newest"  # newest | price_asc | price_desc | sqm_price_asc | area_desc | sold_recent
    )
    page: int = Field(1, ge=1)
    page_size: int = Field(24, ge=1, le=100)


class ImageOut(BaseModel):
    url: str
    w: int | None = None
    h: int | None = None


class ListingCardOut(ORM):
    id: str
    url: str
    status: str
    street_address: str | None
    location_description: str | None
    housing_form: str | None
    housing_form_name: str | None
    asking_price: int | None
    asking_price_text: str | None
    fee: int | None
    sqm_price: int | None
    living_area: float | None
    supplemental_area: float | None
    land_area: float | None
    rooms: float | None
    floor: str | None
    year_built: int | None
    labels: list[str]
    new_construction: bool
    upcoming: bool
    lat: float | None
    lon: float | None
    published_at: datetime | None
    first_seen_at: datetime
    sold_price: int | None
    sold_price_text: str | None
    sold_at: datetime | None
    sold_price_change: str | None
    removed_at: datetime | None
    cover: str | None = None
    image_count: int = 0
    price_dropped: bool = False
    favorite: bool = False
    hidden: bool = False


class PriceChangeOut(ORM):
    old_price: int | None
    new_price: int | None
    changed_at: datetime


class ListingDetailOut(ListingCardOut):
    tenure: str | None
    area_name: str | None
    municipality: str | None
    districts: list[str]
    postcode: str | None
    running_costs: int | None
    has_balcony: bool | None
    has_elevator: bool | None
    energy_class: str | None
    brf_name: str | None
    broker_name: str | None
    broker_agency: str | None
    description: str | None
    last_seen_at: datetime
    images_status: str
    gallery: list[ImageOut] = []
    price_history: list[PriceChangeOut] = []
    note: str | None = None
    regions: list[str] = []


class ListingPage(BaseModel):
    items: list[ListingCardOut]
    total: int
    page: int
    page_size: int


class MapPoint(BaseModel):
    id: str
    lat: float
    lon: float
    status: str
    asking_price: int | None
    street_address: str | None
    rooms: float | None
    living_area: float | None


class ListingStateIn(BaseModel):
    favorite: bool | None = None
    hidden: bool | None = None
    note: str | None = Field(None, max_length=5000)


class RegionPublic(ORM):
    id: int
    name: str
    location_type: str | None
    parent_name: str | None
    item_types: list[str]


class RegionIn(BaseModel):
    location_id: str
    name: str
    location_type: str | None = None
    parent_name: str | None = None
    item_types: list[str] = []
    enabled: bool = True


class RegionUpdate(BaseModel):
    item_types: list[str] | None = None
    enabled: bool | None = None

    @field_validator("item_types")
    @classmethod
    def _dedupe(cls, v):
        return sorted(set(v)) if v is not None else v


class RegionAdminOut(RegionPublic):
    location_id: str
    enabled: bool
    seeded: bool
    created_at: datetime
    last_scan_at: datetime | None
    last_full_scan_at: datetime | None
    last_sold_scan_at: datetime | None
    last_total: int | None
    last_error: str | None
    last_error_at: datetime | None
    listing_count: int = 0
    active_count: int = 0


class NotificationOut(ORM):
    id: int
    kind: str
    channel: str
    status: str
    error: str | None
    created_at: datetime
    sent_at: datetime | None
    listing_id: str | None
    listing_title: str | None = None
    search_name: str | None = None


class JobRunOut(ORM):
    id: int
    job: str
    region_id: int | None
    started_at: datetime
    finished_at: datetime | None
    ok: bool | None
    summary: str | None


class AdminUserOut(UserOut):
    disabled: bool
    last_login_at: datetime | None
    search_count: int = 0


class AdminUserUpdate(BaseModel):
    is_admin: bool | None = None
    disabled: bool | None = None
