export interface User {
  id: number;
  email: string;
  name: string | null;
  display_name: string;
  is_admin: boolean;
  notify_email: boolean;
  created_at: string;
}

export interface AppConfig {
  email_enabled: boolean;
  dev_login: boolean;
}

export interface Criteria {
  region_ids: number[];
  districts: string[];
  housing_forms: string[];
  price_min: number | null;
  price_max: number | null;
  rooms_min: number | null;
  rooms_max: number | null;
  living_area_min: number | null;
  living_area_max: number | null;
  fee_max: number | null;
  sqm_price_max: number | null;
  year_built_min: number | null;
  year_built_max: number | null;
  require_balcony: boolean;
  require_elevator: boolean;
  include_new_construction: boolean;
  keywords: string | null;
  center_lat: number | null;
  center_lon: number | null;
  radius_km: number | null;
  water_distance_max: number | null;
}

export interface SavedSearch extends Criteria {
  id: number;
  name: string;
  enabled: boolean;
  notify_new: boolean;
  notify_price_drop: boolean;
  notify_sold: boolean;
  created_at: string;
  updated_at: string;
  match_count: number | null;
}

export type ListingStatus = "active" | "sold" | "removed" | "all";

export interface ListingQuery extends Criteria {
  status: ListingStatus;
  search_id: number | null;
  favorites_only: boolean;
  subscribed_only: boolean;
  show_hidden: boolean;
  hidden_only: boolean;
  text: string | null;
  sort: string;
  page: number;
  page_size: number;
}

export interface ListingCard {
  id: string;
  url: string;
  status: string;
  street_address: string | null;
  location_description: string | null;
  housing_form: string | null;
  housing_form_name: string | null;
  asking_price: number | null;
  asking_price_text: string | null;
  fee: number | null;
  sqm_price: number | null;
  living_area: number | null;
  supplemental_area: number | null;
  land_area: number | null;
  rooms: number | null;
  floor: string | null;
  year_built: number | null;
  labels: string[];
  new_construction: boolean;
  upcoming: boolean;
  lat: number | null;
  lon: number | null;
  published_at: string | null;
  first_seen_at: string;
  sold_price: number | null;
  sold_price_text: string | null;
  sold_at: string | null;
  sold_price_change: string | null;
  removed_at: string | null;
  water_distance: number | null;
  coastline_distance: number | null;
  cover: string | null;
  image_count: number;
  photos: string[];
  price_dropped: boolean;
  favorite: boolean;
  subscribed: boolean;
  hidden: boolean;
}

export interface ListingDetail extends ListingCard {
  tenure: string | null;
  area_name: string | null;
  municipality: string | null;
  districts: string[];
  postcode: string | null;
  running_costs: number | null;
  has_balcony: boolean | null;
  has_elevator: boolean | null;
  energy_class: string | null;
  brf_name: string | null;
  broker_name: string | null;
  broker_agency: string | null;
  description: string | null;
  last_seen_at: string;
  images_status: string;
  gallery: { url: string; w: number | null; h: number | null }[];
  price_history: { old_price: number | null; new_price: number | null; changed_at: string }[];
  note: string | null;
  regions: string[];
}

export interface ListingPage {
  items: ListingCard[];
  total: number;
  page: number;
  page_size: number;
}

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  status: string;
  asking_price: number | null;
  street_address: string | null;
  rooms: number | null;
  living_area: number | null;
  housing_form: string | null;
  housing_form_name: string | null;
}

export interface Region {
  id: number;
  name: string;
  location_type: string | null;
  parent_name: string | null;
  item_types: string[];
}

export interface AdminRegion extends Region {
  location_id: string;
  enabled: boolean;
  seeded: boolean;
  created_at: string;
  last_scan_at: string | null;
  last_full_scan_at: string | null;
  last_sold_scan_at: string | null;
  last_total: number | null;
  last_error: string | null;
  last_error_at: string | null;
  listing_count: number;
  active_count: number;
}

export interface Facets {
  districts: { name: string; count: number }[];
  housing_forms: { symbol: string; name: string; count: number }[];
  center: [number, number] | null;
}

export interface NotificationItem {
  id: number;
  kind: string;
  channel: string;
  status: string;
  error: string | null;
  created_at: string;
  sent_at: string | null;
  listing_id: string | null;
  listing_title: string | null;
  search_name: string | null;
}

export interface HemnetLocation {
  id: string;
  name: string;
  location_type: string;
  parent_name: string | null;
}

export interface AdminUser extends User {
  disabled: boolean;
  last_login_at: string | null;
  search_count: number;
}

export interface JobRun {
  id: number;
  job: string;
  region_id: number | null;
  started_at: string;
  finished_at: string | null;
  ok: boolean | null;
  summary: string | null;
}

export const emptyCriteria = (): Criteria => ({
  region_ids: [],
  districts: [],
  housing_forms: [],
  price_min: null,
  price_max: null,
  rooms_min: null,
  rooms_max: null,
  living_area_min: null,
  living_area_max: null,
  fee_max: null,
  sqm_price_max: null,
  year_built_min: null,
  year_built_max: null,
  require_balcony: false,
  require_elevator: false,
  include_new_construction: true,
  keywords: null,
  center_lat: null,
  center_lon: null,
  radius_km: null,
  water_distance_max: null,
});

export interface Boundary {
  kind: "district" | "region" | "location";
  key: string;
  name: string;
  source: "osm" | "listings" | null;
  geojson: unknown | null;
  label?: string | null;
  listing_count?: number;
}
