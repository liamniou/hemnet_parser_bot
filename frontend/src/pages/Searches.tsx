import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import CriteriaForm from "../components/CriteriaForm";
import type { Criteria, Region, SavedSearch } from "../types";
import { emptyCriteria } from "../types";
import { mkr, num } from "../format";
import { useSession } from "../App";

type Draft = Omit<SavedSearch, "id" | "created_at" | "updated_at" | "match_count"> & { id?: number };

const newDraft = (): Draft => ({
  ...emptyCriteria(),
  include_new_construction: false,
  name: "",
  enabled: true,
  notify_new: true,
  notify_price_drop: true,
  notify_sold: true,
});

function summary(s: SavedSearch, regions: Region[]): string {
  const parts: string[] = [];
  const rn = s.region_ids.map((id) => regions.find((r) => r.id === id)?.name ?? `#${id}`);
  parts.push(rn.length ? rn.join(", ") : "All regions");
  if (s.districts.length) parts.push(s.districts.join(", "));
  const range = (lo: number | null, hi: number | null, f: (v: number) => string, unit = "") =>
    lo != null || hi != null ? `${lo != null ? f(lo) : "…"}–${hi != null ? f(hi) : "…"}${unit}` : null;
  const p = range(s.price_min, s.price_max, (v) => mkr(v).replace(" Mkr", ""), " Mkr");
  if (p) parts.push(p);
  const r = range(s.rooms_min, s.rooms_max, num, " rum");
  if (r) parts.push(r);
  const a = range(s.living_area_min, s.living_area_max, num, " m²");
  if (a) parts.push(a);
  if (s.fee_max != null) parts.push(`fee ≤ ${num(s.fee_max)}`);
  if (s.require_balcony) parts.push("balcony");
  if (s.require_elevator) parts.push("elevator");
  if (s.radius_km) parts.push(`within ${s.radius_km} km`);
  if (s.keywords) parts.push(`“${s.keywords}”`);
  return parts.join(" · ");
}

function Editor({
  initial,
  regions,
  onDone,
}: {
  initial: Draft;
  regions: Region[];
  onDone: (changed: boolean) => void;
}) {
  const { user, config } = useSession();
  const [d, setD] = useState<Draft>(initial);
  const [count, setCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const criteriaKey = JSON.stringify({ ...d, name: undefined, enabled: undefined });
  useEffect(() => {
    const t = window.setTimeout(() => {
      api<{ count: number }>("/api/searches/preview", { method: "POST", json: d })
        .then((r) => setCount(r.count))
        .catch(() => setCount(null));
    }, 400);
    return () => window.clearTimeout(t);
  }, [criteriaKey]);

  const save = async () => {
    setError(null);
    if (!d.name.trim()) {
      setError("Please give the search a name");
      return;
    }
    try {
      if (d.id) await api(`/api/searches/${d.id}`, { method: "PUT", json: d });
      else await api("/api/searches", { method: "POST", json: d });
      onDone(true);
    } catch (e) {
      setError(String(e));
    }
  };

  const noChannel = !user.notify_email || !config.email_enabled;

  return (
    <div className="card editor">
      <h2>{d.id ? "Edit search" : "New search"}</h2>
      <label className="field">
        <span>Name</span>
        <input value={d.name} autoFocus onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="e.g. 2:a i Vasastan" />
      </label>
      <CriteriaForm value={d} onChange={(c: Criteria) => setD({ ...d, ...c })} regions={regions} />
      <fieldset>
        <legend>Notify me about</legend>
        <div className="checks">
          <label>
            <input type="checkbox" checked={d.notify_new} onChange={(e) => setD({ ...d, notify_new: e.target.checked })} /> New listings
          </label>
          <label>
            <input type="checkbox" checked={d.notify_price_drop} onChange={(e) => setD({ ...d, notify_price_drop: e.target.checked })} /> Price drops
          </label>
          <label>
            <input type="checkbox" checked={d.notify_sold} onChange={(e) => setD({ ...d, notify_sold: e.target.checked })} /> Final sale price
          </label>
          <label>
            <input type="checkbox" checked={d.enabled} onChange={(e) => setD({ ...d, enabled: e.target.checked })} /> Search enabled
          </label>
        </div>
        <p className="muted small">
          Price drop and sale alerts are sent for listings you were notified about or saved.
        </p>
        {noChannel && (
          <p className="banner warn">
            Email notifications are off. Turn them on in <Link to="/settings">Settings</Link>.
          </p>
        )}
      </fieldset>
      <div className="row between">
        <span className="muted">
          {count == null ? "…" : `${count} listings for sale match right now`}
        </span>
        <div className="row">
          <button onClick={() => onDone(false)}>Cancel</button>
          <button className="primary" onClick={save}>
            Save search
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function Searches() {
  const [items, setItems] = useState<SavedSearch[] | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [editing, setEditing] = useState<Draft | null>(null);

  const load = () => api<SavedSearch[]>("/api/searches").then(setItems);
  useEffect(() => {
    load();
    api<Region[]>("/api/regions").then(setRegions);
  }, []);

  const toggle = async (s: SavedSearch) => {
    await api(`/api/searches/${s.id}`, { method: "PUT", json: { ...s, enabled: !s.enabled } });
    load();
  };

  const remove = async (s: SavedSearch) => {
    if (!window.confirm(`Delete search "${s.name}"?`)) return;
    await api(`/api/searches/${s.id}`, { method: "DELETE" });
    load();
  };

  if (editing)
    return (
      <Editor
        initial={editing}
        regions={regions}
        onDone={(changed) => {
          setEditing(null);
          if (changed) load();
        }}
      />
    );

  return (
    <div>
      <div className="row between">
        <h1>My searches</h1>
        <button className="primary" onClick={() => setEditing(newDraft())}>
          <Plus size={16} /> New search
        </button>
      </div>
      <p className="muted">
        You get notified when a new listing matches one of your searches, and later when its price drops or it
        sells.
      </p>
      {items && items.length === 0 && (
        <div className="card empty">No searches yet. Create one to start receiving alerts.</div>
      )}
      <div className="search-list">
        {items?.map((s) => (
          <div key={s.id} className={`card search-item ${s.enabled ? "" : "dim"}`}>
            <div>
              <h3>{s.name}</h3>
              <p className="muted small">{summary(s, regions)}</p>
              <p className="small">
                <Link to={`/?search=${s.id}`}>{s.match_count ?? 0} matching listings for sale →</Link>
              </p>
              <p className="small muted">
                Alerts:{" "}
                {[s.notify_new && "new", s.notify_price_drop && "price drops", s.notify_sold && "sold"]
                  .filter(Boolean)
                  .join(", ") || "none"}
              </p>
            </div>
            <div className="row">
              <label className="switch" title={s.enabled ? "Enabled" : "Paused"}>
                <input type="checkbox" checked={s.enabled} onChange={() => toggle(s)} />
                <span />
              </label>
              <button className="icon" title="Edit" onClick={() => setEditing({ ...s })}>
                <Pencil size={16} />
              </button>
              <button className="icon danger" title="Delete" onClick={() => remove(s)}>
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
