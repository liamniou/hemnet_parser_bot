import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BookmarkPlus, Columns2, Grid3x3, Map as MapIcon, SlidersHorizontal, X } from "lucide-react";
import { api } from "../api";
import CriteriaForm from "../components/CriteriaForm";
import ListingCardView from "../components/ListingCard";
import ListingsMap from "../components/ListingsMap";
import type { ListingCard, ListingPage, ListingQuery, MapPoint, Region, SavedSearch } from "../types";
import { emptyCriteria } from "../types";

const STORAGE_KEY = "hw.listingQuery";
const VIEW_KEY = "hw.listingView";
type View = "grid" | "split" | "map";

const defaultQuery = (): ListingQuery => ({
  ...emptyCriteria(),
  status: "active",
  search_id: null,
  favorites_only: false,
  subscribed_only: false,
  show_hidden: false,
  hidden_only: false,
  text: null,
  sort: "newest",
  page: 1,
  page_size: 24,
});

function loadQuery(): ListingQuery {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaultQuery(), ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return defaultQuery();
}

export default function Listings() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState<ListingQuery>(() => {
    const q = loadQuery();
    const sid = params.get("search");
    return sid ? { ...q, search_id: Number(sid), page: 1 } : q;
  });
  const [page, setPage] = useState<ListingPage | null>(null);
  const [points, setPoints] = useState<MapPoint[]>([]);
  const [regions, setRegions] = useState<Region[]>([]);
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [view, setViewState] = useState<View>(() => {
    const v = localStorage.getItem(VIEW_KEY);
    return v === "grid" || v === "map" || v === "split" ? v : "split";
  });
  const setView = (v: View) => {
    localStorage.setItem(VIEW_KEY, v);
    setViewState(v);
  };
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [showFilters, setShowFilters] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Region[]>("/api/regions").then(setRegions).catch(() => {});
    api<SavedSearch[]>("/api/searches").then(setSearches).catch(() => {});
  }, []);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(query));
    if (view === "map") return;
    setLoading(true);
    setError(null);
    api<ListingPage>("/api/listings/query", { method: "POST", json: query })
      .then(setPage)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [query, view, reloadKey]);

  // Only the full map shows every result; the split map shows the current page.
  const pointsKey = JSON.stringify({ ...query, page: 1 });
  useEffect(() => {
    if (view !== "map") return;
    api<MapPoint[]>("/api/listings/map", { method: "POST", json: JSON.parse(pointsKey) })
      .then(setPoints)
      .catch((e) => setError(String(e)));
  }, [pointsKey, view]);

  const pagePoints = useMemo<MapPoint[]>(
    () =>
      (page?.items ?? [])
        .filter((l) => l.lat != null && l.lon != null)
        .map((l) => ({
          id: l.id,
          lat: l.lat!,
          lon: l.lon!,
          status: l.status,
          asking_price: l.status === "sold" && l.sold_price ? l.sold_price : l.asking_price,
          street_address: l.street_address,
          rooms: l.rooms,
          living_area: l.living_area,
          housing_form: l.housing_form,
          housing_form_name: l.housing_form_name,
        })),
    [page],
  );
  const highlight = useMemo(
    () => pagePoints.find((p) => p.id === hoveredId) ?? null,
    [pagePoints, hoveredId],
  );

  const goToPage = (n: number) => {
    setQuery((q) => ({ ...q, page: n }));
    window.scrollTo(0, 0);
  };

  const update = useCallback((patch: Partial<ListingQuery>) => {
    setQuery((q) => ({ ...q, page: 1, ...patch }));
  }, []);

  const toggleFavorite = async (l: ListingCard) => {
    await api(`/api/listings/${l.id}/state`, { method: "PUT", json: { favorite: !l.favorite } });
    setPage((p) =>
      p ? { ...p, items: p.items.map((x) => (x.id === l.id ? { ...x, favorite: !l.favorite } : x)) } : p,
    );
  };

  const toggleSubscribe = async (l: ListingCard) => {
    const subscribed = !l.subscribed;
    await api(`/api/listings/${l.id}/state`, { method: "PUT", json: { subscribed } });
    setPage((p) => {
      if (!p) return p;
      if (!subscribed && query.subscribed_only) {
        return { ...p, items: p.items.filter((x) => x.id !== l.id), total: p.total - 1 };
      }
      return { ...p, items: p.items.map((x) => (x.id === l.id ? { ...x, subscribed } : x)) };
    });
  };

  const [undo, setUndo] = useState<ListingCard | null>(null);
  const setHidden = async (l: ListingCard, hidden: boolean) => {
    await api(`/api/listings/${l.id}/state`, { method: "PUT", json: { hidden } });
    setPage((p) => {
      if (!p) return p;
      // Hiding removes a card from the normal list; unhiding removes it from the "Hidden" list.
      if (hidden !== query.hidden_only) {
        return { ...p, items: p.items.filter((x) => x.id !== l.id), total: p.total - 1 };
      }
      return { ...p, items: p.items.map((x) => (x.id === l.id ? { ...x, hidden } : x)) };
    });
    // Undo of a card that already left the list: reload so it returns to its place.
    if (!hidden && !query.hidden_only && page && !page.items.some((x) => x.id === l.id)) {
      setReloadKey((k) => k + 1);
    }
    if (hoveredId === l.id) setHoveredId(null);
    setUndo(hidden ? l : null);
  };
  useEffect(() => {
    if (!undo) return;
    const t = window.setTimeout(() => setUndo(null), 8000);
    return () => window.clearTimeout(t);
  }, [undo]);

  const saveAsSearch = async () => {
    const name = window.prompt("Name for this search:", "My search");
    if (!name) return;
    const { status: _s, search_id: _i, favorites_only: _f, subscribed_only: _w, show_hidden: _h, hidden_only: _ho, text: _t, sort: _o, page: _p, page_size: _z, ...criteria } = query;
    await api("/api/searches", { method: "POST", json: { ...criteria, name } });
    navigate("/searches");
  };

  const activeSearch = searches.find((s) => s.id === query.search_id);
  const pages = page ? Math.max(1, Math.ceil(page.total / page.page_size)) : 1;

  return (
    <div className="listings-page">
      <div className="toolbar">
        <select
          value={query.search_id ?? ""}
          onChange={(e) => {
            const v = e.target.value ? Number(e.target.value) : null;
            update({ search_id: v });
            setParams(v ? { search: String(v) } : {});
          }}
        >
          <option value="">All listings (custom filter)</option>
          {searches.map((s) => (
            <option key={s.id} value={s.id}>
              🔎 {s.name}
            </option>
          ))}
        </select>
        <select value={query.status} onChange={(e) => update({ status: e.target.value as ListingQuery["status"] })}>
          <option value="active">For sale</option>
          <option value="sold">Sold</option>
          <option value="removed">Removed</option>
          <option value="all">All statuses</option>
        </select>
        <select value={query.sort} onChange={(e) => update({ sort: e.target.value })}>
          <option value="newest">Newest</option>
          <option value="price_asc">Price ↑</option>
          <option value="price_desc">Price ↓</option>
          <option value="sqm_price_asc">Price/m² ↑</option>
          <option value="area_desc">Largest</option>
          <option value="sold_recent">Recently sold</option>
        </select>
        <input
          className="grow"
          placeholder="Search address…"
          value={query.text ?? ""}
          onChange={(e) => update({ text: e.target.value || null })}
        />
        <label className="inline">
          <input
            type="checkbox"
            checked={query.favorites_only}
            onChange={(e) => update({ favorites_only: e.target.checked })}
          />{" "}
          Saved
        </label>
        <label className="inline" title="Listings you get price-drop and sale emails for">
          <input
            type="checkbox"
            checked={query.subscribed_only}
            onChange={(e) => update({ subscribed_only: e.target.checked })}
          />{" "}
          Watching
        </label>
        <label className="inline">
          <input
            type="checkbox"
            checked={query.hidden_only}
            onChange={(e) => update({ hidden_only: e.target.checked, show_hidden: false })}
          />{" "}
          Hidden
        </label>
        {!query.search_id && (
          <button onClick={() => setShowFilters((s) => !s)} className={showFilters ? "on" : ""}>
            <SlidersHorizontal size={16} /> Filters
          </button>
        )}
        <div className="seg">
          <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")} title="Cards only">
            <Grid3x3 size={16} />
          </button>
          <button className={view === "split" ? "on" : ""} onClick={() => setView("split")} title="Cards and map">
            <Columns2 size={16} />
          </button>
          <button className={view === "map" ? "on" : ""} onClick={() => setView("map")} title="Map only">
            <MapIcon size={16} />
          </button>
        </div>
      </div>

      {activeSearch && (
        <div className="banner">
          Showing listings matching your search <b>{activeSearch.name}</b>.{" "}
          <button className="link" onClick={() => { update({ search_id: null }); setParams({}); }}>
            Clear
          </button>
        </div>
      )}

      {showFilters && !query.search_id && (
        <div className="card filters">
          <div className="row between">
            <h3>Filters</h3>
            <div className="row">
              <button onClick={saveAsSearch}>
                <BookmarkPlus size={16} /> Save as search &amp; get alerts
              </button>
              <button onClick={() => setQuery({ ...defaultQuery(), status: query.status, sort: query.sort })}>
                Reset
              </button>
              <button className="icon" onClick={() => setShowFilters(false)}>
                <X size={16} />
              </button>
            </div>
          </div>
          <CriteriaForm value={query} onChange={(c) => update(c)} regions={regions} compact />
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {undo && (
        <div className="toast" role="status">
          Hidden <b>{undo.street_address ?? "listing"}</b>. You can find it under “Hidden”.
          <button className="link" onClick={() => setHidden(undo, false)}>
            Undo
          </button>
        </div>
      )}

      {view === "map" ? (
        <>
          <p className="muted small">{points.length} listings with coordinates{loading && " · loading…"}</p>
          <ListingsMap points={points} />
        </>
      ) : (
        <>
          <p className="muted small">
            {page ? `${page.total} listings` : ""}
            {loading && " · loading…"}
          </p>
          {page && page.items.length === 0 && !loading && (
            <div className="empty card">
              No listings found.{" "}
              {regions.length === 0 && "An admin needs to add regions to scrape first."}
            </div>
          )}
          <div className={view === "split" ? "split" : ""}>
            <div>
              <div className="grid">
                {page?.items.map((l) => (
                  <ListingCardView
                    key={l.id}
                    l={l}
                    onFavorite={toggleFavorite}
                    onHide={(x) => setHidden(x, !x.hidden)}
                    onSubscribe={toggleSubscribe}
                    onHover={view === "split" ? setHoveredId : undefined}
                    highlighted={view === "split" && hoveredId === l.id}
                  />
                ))}
              </div>
              {pages > 1 && (
                <div className="pager">
                  <button disabled={query.page <= 1} onClick={() => goToPage(query.page - 1)}>
                    ← Prev
                  </button>
                  <span>
                    Page {query.page} / {pages}
                  </span>
                  <button disabled={query.page >= pages} onClick={() => goToPage(query.page + 1)}>
                    Next →
                  </button>
                </div>
              )}
            </div>
            {view === "split" && (
              <aside className="split-map">
                <ListingsMap
                  points={pagePoints}
                  highlight={highlight}
                  onHover={setHoveredId}
                  className="side-map"
                />
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  );
}
