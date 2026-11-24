import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Pause, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../api";
import { Chips } from "../components/CriteriaForm";
import type { AdminRegion, AdminUser, HemnetLocation, JobRun } from "../types";
import { ago, bytes, dateTime, num } from "../format";
import { useSession } from "../App";

type ItemType = { value: string; label: string };

function AddRegion({ itemTypes, onAdded }: { itemTypes: ItemType[]; onAdded: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<HemnetLocation[]>([]);
  const [picked, setPicked] = useState<HemnetLocation | null>(null);
  const [types, setTypes] = useState<string[]>(["bostadsratt"]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (picked || q.trim().length < 2) {
      setResults([]);
      return;
    }
    const t = window.setTimeout(() => {
      api<HemnetLocation[]>(`/api/admin/locations?q=${encodeURIComponent(q)}`)
        .then(setResults)
        .catch((e) => setError(String(e)));
    }, 350);
    return () => window.clearTimeout(t);
  }, [q, picked]);

  const add = async () => {
    if (!picked) return;
    setError(null);
    try {
      await api("/api/admin/regions", {
        method: "POST",
        json: {
          location_id: picked.id,
          name: picked.name,
          location_type: picked.location_type,
          parent_name: picked.parent_name,
          item_types: types,
        },
      });
      setPicked(null);
      setQ("");
      onAdded();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="card">
      <h3>Add region</h3>
      <div className="typeahead">
        <input
          placeholder="Search Hemnet locations, e.g. Solna, Vasastan, Göteborgs kommun…"
          value={picked ? `${picked.name} (${picked.location_type})` : q}
          onChange={(e) => {
            setPicked(null);
            setQ(e.target.value);
          }}
        />
        {results.length > 0 && (
          <ul className="dropdown">
            {results.map((r) => (
              <li key={r.id} onClick={() => setPicked(r)}>
                <b>{r.name}</b> <span className="muted small">{r.location_type}{r.parent_name && ` · ${r.parent_name}`}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <label className="field">
        <span>
          Property types <small className="muted">(none selected = all types)</small>
        </span>
        <Chips options={itemTypes} selected={types} onChange={setTypes} />
      </label>
      <button className="primary" disabled={!picked} onClick={add}>
        <Plus size={16} /> Add region
      </button>
      <p className="muted small">
        The first scan archives every current listing without notifying anyone; later scans announce new listings.
      </p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Regions() {
  const [regions, setRegions] = useState<AdminRegion[]>([]);
  const [itemTypes, setItemTypes] = useState<ItemType[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<AdminRegion[]>("/api/admin/regions").then(setRegions), []);
  useEffect(() => {
    load();
    api<ItemType[]>("/api/admin/item-types").then(setItemTypes);
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const label = (v: string) => itemTypes.find((t) => t.value === v)?.label ?? v;

  return (
    <div>
      <AddRegion itemTypes={itemTypes} onAdded={load} />
      {error && <p className="error">{error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Region</th>
            <th>Types</th>
            <th>Listings</th>
            <th>Last scan</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {regions.map((r) => (
            <tr key={r.id} className={r.enabled ? "" : "dim"}>
              <td>
                <b>{r.name}</b>
                <div className="muted small">
                  {r.location_type}
                  {r.parent_name && ` · ${r.parent_name}`} · id {r.location_id}
                </div>
              </td>
              <td className="small">{r.item_types.length ? r.item_types.map(label).join(", ") : "All"}</td>
              <td className="small">
                {num(r.active_count)} for sale
                <div className="muted">
                  {num(r.listing_count)} archived · Hemnet total {num(r.last_total)}
                </div>
              </td>
              <td className="small">
                {ago(r.last_scan_at)}
                <div className="muted">full {ago(r.last_full_scan_at)} · sold {ago(r.last_sold_scan_at)}</div>
              </td>
              <td className="small">
                {!r.seeded ? (
                  <span className="badge">Seeding…</span>
                ) : r.last_error ? (
                  <span className="error" title={r.last_error}>
                    Error {ago(r.last_error_at)}
                  </span>
                ) : (
                  <span className="ok">OK</span>
                )}
              </td>
              <td className="nowrap">
                <button
                  className="icon"
                  title="Scan now"
                  onClick={() => act(() => api(`/api/admin/regions/${r.id}/scan?mode=auto`, { method: "POST" }))}
                >
                  <RefreshCw size={16} />
                </button>
                <button
                  className="icon"
                  title="Check sold prices now"
                  onClick={() => act(() => api(`/api/admin/regions/${r.id}/scan?mode=sold`, { method: "POST" }))}
                >
                  🔨
                </button>
                <button
                  className="icon"
                  title={r.enabled ? "Pause" : "Resume"}
                  onClick={() =>
                    act(() => api(`/api/admin/regions/${r.id}`, { method: "PATCH", json: { enabled: !r.enabled } }))
                  }
                >
                  {r.enabled ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <button
                  className="icon danger"
                  title="Delete"
                  onClick={() => {
                    if (!window.confirm(`Delete region ${r.name}?`)) return;
                    const purge = window.confirm(
                      "Also delete listings (and archived images) that only belong to this region?",
                    );
                    act(() => api(`/api/admin/regions/${r.id}?purge=${purge}`, { method: "DELETE" }));
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {regions.some((r) => r.last_total != null && r.last_total > 2500) && (
        <p className="banner warn">
          Some regions have more than 2 500 listings, the most Hemnet returns for one search. Only the newest 2 500
          are archived and removal detection is skipped there; split them into smaller areas (districts).
        </p>
      )}
    </div>
  );
}

function Users() {
  const { user: me } = useSession();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const load = () => api<AdminUser[]>("/api/admin/users").then(setUsers);
  useEffect(() => {
    load();
  }, []);
  const patch = async (u: AdminUser, body: Partial<AdminUser>) => {
    await api(`/api/admin/users/${u.id}`, { method: "PATCH", json: body });
    load();
  };
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Email</th>
          <th>Name</th>
          <th>Searches</th>
          <th>Joined</th>
          <th>Last login</th>
          <th>Admin</th>
          <th>Disabled</th>
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.id} className={u.disabled ? "dim" : ""}>
            <td>
              {u.email}
              {!u.notify_email && <span className="muted small"> (alerts off)</span>}
            </td>
            <td className="small">{u.name ?? "–"}</td>
            <td>{u.search_count}</td>
            <td className="small">{dateTime(u.created_at)}</td>
            <td className="small">{dateTime(u.last_login_at)}</td>
            <td>
              <input
                type="checkbox"
                checked={u.is_admin}
                disabled={u.id === me.id}
                onChange={(e) => patch(u, { is_admin: e.target.checked })}
              />
            </td>
            <td>
              <input
                type="checkbox"
                checked={u.disabled}
                disabled={u.id === me.id}
                onChange={(e) => patch(u, { disabled: e.target.checked })}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface Stats {
  listings: Record<string, number>;
  images: Record<string, number>;
  pending_details: number;
  notifications: Record<string, number>;
  users: number;
  searches: number;
  images_bytes: number;
  db_bytes: number;
  disk_free_bytes: number | null;
  running_scans: number[];
  settings: Record<string, string | number | boolean>;
}

function System() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<JobRun[]>([]);
  useEffect(() => {
    const load = () => {
      api<Stats>("/api/admin/stats").then(setStats);
      api<JobRun[]>("/api/admin/jobs?limit=40").then(setJobs);
    };
    load();
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, []);
  if (!stats) return <p className="muted">Loading…</p>;
  const kv = (o: Record<string, number>) =>
    Object.entries(o)
      .map(([k, v]) => `${k}: ${num(v)}`)
      .join(" · ") || "–";
  return (
    <div>
      <div className="stats">
        <div className="card">
          <h4>Listings</h4>
          <p>{kv(stats.listings)}</p>
          <p className="muted small">Detail pages queued: {num(stats.pending_details)}</p>
        </div>
        <div className="card">
          <h4>Image archive</h4>
          <p>{kv(stats.images)}</p>
          <p className="muted small">
            {bytes(stats.images_bytes)} images · {bytes(stats.db_bytes)} DB · {bytes(stats.disk_free_bytes)} free
          </p>
        </div>
        <div className="card">
          <h4>Notifications</h4>
          <p>{kv(stats.notifications)}</p>
          <p className="muted small">
            {stats.users} users · {stats.searches} searches
          </p>
        </div>
        <div className="card">
          <h4>Settings</h4>
          <p className="small">
            {Object.entries(stats.settings)
              .map(([k, v]) => `${k}=${v}`)
              .join(" · ")}
          </p>
        </div>
      </div>
      <h3>Recent jobs</h3>
      <table className="table">
        <thead>
          <tr>
            <th>Started</th>
            <th>Job</th>
            <th>Region</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td className="nowrap small">{dateTime(j.started_at)}</td>
              <td className="nowrap">{j.job}</td>
              <td>{j.region_id ?? "–"}</td>
              <td className={`small ${j.ok === false ? "error" : ""}`}>
                {j.finished_at ? j.summary : "running…"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Admin() {
  return (
    <div>
      <h1>Admin</h1>
      <nav className="tabs">
        <NavLink to="/admin/regions">Regions</NavLink>
        <NavLink to="/admin/users">Users</NavLink>
        <NavLink to="/admin/system">System</NavLink>
      </nav>
      <Routes>
        <Route path="regions" element={<Regions />} />
        <Route path="users" element={<Users />} />
        <Route path="system" element={<System />} />
        <Route path="*" element={<Navigate to="regions" replace />} />
      </Routes>
    </div>
  );
}
