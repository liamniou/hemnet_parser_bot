import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Criteria, Facets, Region } from "../types";
import RadiusPicker from "./RadiusPicker";
import { AreaHover, BoundaryMap, useBoundaries, type AreaRef } from "./Boundaries";

interface Props {
  value: Criteria;
  onChange: (c: Criteria) => void;
  regions: Region[];
  compact?: boolean;
}

type NumKey = {
  [K in keyof Criteria]: Criteria[K] extends number | null ? K : never;
}[keyof Criteria];

function NumInput({
  label,
  k,
  value,
  onChange,
  step,
  placeholder,
}: {
  label?: string;
  k: NumKey;
  value: Criteria;
  onChange: (c: Criteria) => void;
  step?: number;
  placeholder?: string;
}) {
  const v = value[k];
  return (
    <input
      type="number"
      inputMode="decimal"
      aria-label={label ?? k}
      placeholder={placeholder}
      step={step}
      min={0}
      value={v ?? ""}
      onChange={(e) => onChange({ ...value, [k]: e.target.value === "" ? null : Number(e.target.value) })}
    />
  );
}

function Range(props: {
  label: string;
  min: NumKey;
  max: NumKey;
  value: Criteria;
  onChange: (c: Criteria) => void;
  step?: number;
  unit?: string;
}) {
  return (
    <label className="field">
      <span>
        {props.label} {props.unit && <small className="muted">({props.unit})</small>}
      </span>
      <div className="range">
        <NumInput {...props} k={props.min} label={`${props.label} min`} placeholder="min" />
        <span className="muted">–</span>
        <NumInput {...props} k={props.max} label={`${props.label} max`} placeholder="max" />
      </div>
    </label>
  );
}

export function Chips({
  options,
  selected,
  onChange,
  empty = "Any",
  area,
}: {
  area?: (value: string) => AreaRef;
  options: { value: string; label: string; count?: number }[];
  selected: string[];
  onChange: (v: string[]) => void;
  empty?: string;
}) {
  if (!options.length) return <span className="muted small">{empty}</span>;
  return (
    <div className="chips">
      {options.map((o) => {
        const on = selected.includes(o.value);
        const chip = (
          <button
            type="button"
            key={o.value}
            className={`chip ${on ? "on" : ""}`}
            onClick={() => onChange(on ? selected.filter((x) => x !== o.value) : [...selected, o.value])}
          >
            {o.label}
            {o.count != null && <small> {o.count}</small>}
          </button>
        );
        return area ? (
          <AreaHover key={o.value} area={area(o.value)}>
            {chip}
          </AreaHover>
        ) : (
          chip
        );
      })}
    </div>
  );
}

/** Saved-search editor: all selected areas on one map (districts, else whole regions). */
function SelectedAreas({ districts, regionIds }: { districts: string[]; regionIds: number[] }) {
  const borders = useBoundaries(districts, regionIds);
  const wanted = districts.length || regionIds.length;
  return (
    <BoundaryMap
      items={borders}
      height={220}
      caption={
        borders.length < wanted
          ? `${borders.length} of ${wanted} selected areas outlined (looking up the rest…)`
          : `Selected ${districts.length ? "areas" : "regions"}: dashed outlines are approximate (around listings)`
      }
    />
  );
}

export default function CriteriaForm({ value, onChange, regions, compact }: Props) {
  const [facets, setFacets] = useState<Facets>({ districts: [], housing_forms: [], center: null });
  const [districtFilter, setDistrictFilter] = useState("");
  const [showMap, setShowMap] = useState(value.radius_km != null);
  const regionKey = value.region_ids.join(",");

  useEffect(() => {
    api<Facets>(`/api/listings/facets?region_ids=${regionKey}`).then(setFacets).catch(() => {});
  }, [regionKey]);

  const districtOptions = useMemo(() => {
    const q = districtFilter.trim().toLowerCase();
    const all = facets.districts.map((d) => ({ value: d.name, label: d.name, count: d.count }));
    // Keep selected districts visible even if they no longer have active listings.
    for (const d of value.districts) if (!all.some((o) => o.value === d)) all.push({ value: d, label: d, count: 0 });
    return all
      .filter((o) => value.districts.includes(o.value) || !q || o.label.toLowerCase().includes(q))
      .sort((a, b) => Number(value.districts.includes(b.value)) - Number(value.districts.includes(a.value)) || (b.count ?? 0) - (a.count ?? 0))
      .slice(0, q ? 60 : 30);
  }, [facets.districts, districtFilter, value.districts]);

  return (
    <div className={`criteria ${compact ? "compact" : ""}`}>
      <div className="field">
        <span>Regions</span>
        <Chips
          options={regions.map((r) => ({ value: String(r.id), label: r.name }))}
          selected={value.region_ids.map(String)}
          onChange={(v) => onChange({ ...value, region_ids: v.map(Number) })}
          empty="No regions configured yet"
          area={(v) => ({ regionId: Number(v) })}
        />
      </div>

      <div className="field">
        <span>
          Areas / districts <small className="muted">(empty = whole region)</small>
        </span>
        <input
          aria-label="Filter districts"
          placeholder="Filter districts…"
          value={districtFilter}
          onChange={(e) => setDistrictFilter(e.target.value)}
        />
        <Chips
          options={districtOptions}
          selected={value.districts}
          onChange={(v) => onChange({ ...value, districts: v })}
          empty="Districts appear once listings have been scraped"
          area={(v) => ({ district: v })}
        />
        {!compact && (value.districts.length > 0 || value.region_ids.length > 0) && (
          <SelectedAreas districts={value.districts} regionIds={value.region_ids} />
        )}
      </div>

      <div className="field">
        <span>Property type</span>
        <Chips
          options={facets.housing_forms.map((f) => ({ value: f.symbol, label: f.name, count: f.count }))}
          selected={value.housing_forms}
          onChange={(v) => onChange({ ...value, housing_forms: v })}
        />
      </div>

      <div className="grid2">
        <Range label="Price" unit="kr" min="price_min" max="price_max" value={value} onChange={onChange} step={100000} />
        <Range label="Rooms" min="rooms_min" max="rooms_max" value={value} onChange={onChange} step={0.5} />
        <Range label="Living area" unit="m²" min="living_area_min" max="living_area_max" value={value} onChange={onChange} />
        <Range label="Year built" min="year_built_min" max="year_built_max" value={value} onChange={onChange} />
        <label className="field">
          <span>
            Max fee <small className="muted">(kr/mån)</small>
          </span>
          <NumInput k="fee_max" value={value} onChange={onChange} step={500} placeholder="any" />
        </label>
        <label className="field">
          <span>
            Max price per m² <small className="muted">(kr)</small>
          </span>
          <NumInput k="sqm_price_max" value={value} onChange={onChange} step={5000} placeholder="any" />
        </label>
      </div>

      <div className="checks">
        <label>
          <input
            type="checkbox"
            checked={value.require_balcony}
            onChange={(e) => onChange({ ...value, require_balcony: e.target.checked })}
          />{" "}
          Balcony
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.require_elevator}
            onChange={(e) => onChange({ ...value, require_elevator: e.target.checked })}
          />{" "}
          Elevator
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.include_new_construction}
            onChange={(e) => onChange({ ...value, include_new_construction: e.target.checked })}
          />{" "}
          Include new construction
        </label>
        <label className="inline">
          Close to water
          <select
            aria-label="Close to water"
            value={value.water_distance_max ?? ""}
            onChange={(e) => onChange({ ...value, water_distance_max: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">Any distance</option>
            {[100, 200, 300, 500, 1000].map((m) => (
              <option key={m} value={m}>
                within {m >= 1000 ? `${m / 1000} km` : `${m} m`}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="field">
        <span>
          Keywords <small className="muted">(comma separated, any match; prefix with - to exclude)</small>
        </span>
        <input
          placeholder="e.g. kakelugn, takterrass, -bottenvåning"
          value={value.keywords ?? ""}
          onChange={(e) => onChange({ ...value, keywords: e.target.value || null })}
        />
      </label>

      <div className="field">
        <label className="inline">
          <input
            type="checkbox"
            checked={showMap}
            onChange={(e) => {
              setShowMap(e.target.checked);
              if (!e.target.checked) onChange({ ...value, center_lat: null, center_lon: null, radius_km: null });
            }}
          />{" "}
          Limit to distance from a point
        </label>
        {showMap && <RadiusPicker value={value} onChange={onChange} fallbackCenter={facets.center} />}
      </div>
    </div>
  );
}
