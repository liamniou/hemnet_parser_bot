import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import type { GeoJsonObject } from "geojson";
import { api } from "../api";
import type { Boundary } from "../types";

// ---------------------------------------------------------------- loading (cached per session)

const cache = new Map<string, Promise<Boundary | null>>();
// Settled results, so previews can render a cached border on their very first frame.
const settled = new Map<string, Boundary | null>();

function load(cacheKey: string, fetcher: () => Promise<Boundary | null>) {
  let p = cache.get(cacheKey);
  if (!p) {
    p = fetcher().then(
      (b) => {
        settled.set(cacheKey, b);
        return b;
      },
      () => {
        cache.delete(cacheKey);
        return null;
      },
    );
    cache.set(cacheKey, p);
  }
  return p;
}

const fetchOne = (body: { districts?: string[]; region_ids?: number[] }) =>
  api<Boundary[]>("/api/listings/boundaries", {
    method: "POST",
    json: body,
  }).then((r) => r[0] ?? null);

export type AreaRef =
  | { district: string }
  | { regionId: number }
  | { location: { id: string; name: string } };

const refKey = (ref: AreaRef) =>
  "district" in ref
    ? `d:${ref.district}`
    : "regionId" in ref
      ? `r:${ref.regionId}`
      : `l:${ref.location.id}`;

export function loadBoundary(ref: AreaRef): Promise<Boundary | null> {
  return load(refKey(ref), () => {
    if ("district" in ref) return fetchOne({ districts: [ref.district] });
    if ("regionId" in ref) return fetchOne({ region_ids: [ref.regionId] });
    const { id, name } = ref.location;
    const qs = new URLSearchParams({ location_id: id, name });
    return api<Boundary>(`/api/admin/boundary-preview?${qs}`);
  });
}

const peekBoundary = (ref: AreaRef) => settled.get(refKey(ref));

/** Borders for the selected areas; districts take precedence over whole regions. */
export function useBoundaries(
  districts: string[],
  regionIds: number[],
): Boundary[] {
  const [items, setItems] = useState<Boundary[]>([]);
  const key = JSON.stringify([districts, regionIds]);
  useEffect(() => {
    let live = true;
    const refs: AreaRef[] = districts.length
      ? districts.map((d) => ({ district: d }))
      : regionIds.map((id) => ({ regionId: id }));
    if (!refs.length) {
      setItems([]);
      return;
    }
    // Draw each border as soon as it arrives; uncached Hemnet lookups take a second or two.
    const got: (Boundary | null)[] = refs.map(() => null);
    refs.forEach((ref, i) =>
      loadBoundary(ref).then((b) => {
        got[i] = b;
        if (live) setItems(got.filter((x): x is Boundary => !!x?.geojson));
      }),
    );
    return () => {
      live = false;
    };
  }, [key]);
  return items;
}

// ---------------------------------------------------------------- drawing

export const borderStyle = (b: Boundary): L.PathOptions => ({
  color: "#0f766e",
  weight: 2.5,
  opacity: 0.9,
  dashArray: b.source === "listings" ? "6 5" : undefined,
  fillColor: "#14b8a6",
  fillOpacity: 0.07,
});

export function BoundaryLayers({ items }: { items: Boundary[] }) {
  return (
    <>
      {items.map((b) => (
        <GeoJSON
          key={`${b.kind}:${b.key}:${b.source}`}
          data={b.geojson as GeoJsonObject}
          style={() => borderStyle(b)}
          interactive={false}
        />
      ))}
    </>
  );
}

export function boundsOf(items: Boundary[]): L.LatLngBounds | null {
  let bounds: L.LatLngBounds | null = null;
  for (const b of items) {
    const bb = L.geoJSON(b.geojson as GeoJsonObject).getBounds();
    if (bb.isValid()) bounds = bounds ? bounds.extend(bb) : bb;
  }
  return bounds;
}

export const sourceLabel = (b: Boundary | null) =>
  !b || !b.geojson
    ? "No border found"
    : b.source === "hemnet"
      ? "Border from Hemnet"
      : `Approximate outline around ${b.listing_count ?? ""} listings`;

// ---------------------------------------------------------------- previews

function Fit({ items }: { items: Boundary[] }) {
  const map = useMap();
  useEffect(() => {
    const b = boundsOf(items);
    if (b) map.fitBounds(b, { padding: [12, 12] });
  }, [items, map]);
  return null;
}

/** Small map showing one or more borders, with where they came from. */
export function BoundaryMap({
  items,
  height = 180,
  loading,
  caption,
}: {
  items: Boundary[];
  height?: number;
  loading?: boolean;
  caption?: string;
}) {
  const drawn = items.filter((b) => b.geojson);
  return (
    <div className="boundary-map">
      <MapContainer
        center={[59.33, 18.07]}
        zoom={10}
        style={{ height }}
        zoomControl={false}
        attributionControl={false}
        dragging={false}
        scrollWheelZoom={false}
        doubleClickZoom={false}
        keyboard={false}
      >
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <BoundaryLayers items={drawn} />
        <Fit items={drawn} />
      </MapContainer>
      <div className="muted small boundary-caption">
        {caption ??
          (loading
            ? "Looking up border…"
            : items.length === 1
              ? sourceLabel(items[0])
              : `${drawn.length} of ${items.length} areas outlined`)}
      </div>
    </div>
  );
}

export function AreaPreview({
  area,
  height,
}: {
  area: AreaRef;
  height?: number;
}) {
  const [b, setB] = useState<Boundary | null | undefined>(() =>
    peekBoundary(area),
  );
  const key = JSON.stringify(area);
  useEffect(() => {
    let live = true;
    setB(peekBoundary(area));
    loadBoundary(area).then((x) => live && setB(x));
    return () => {
      live = false;
    };
  }, [key]);
  return (
    <BoundaryMap
      items={b ? [b] : []}
      height={height}
      loading={b === undefined}
    />
  );
}

/** Shows `preview` in a floating card while the pointer rests on `children`. */
export function HoverPreview({
  preview,
  onIntent,
  children,
}: {
  preview: () => ReactNode;
  /** Called as soon as the pointer enters, to start loading before the card opens. */
  onIntent?: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const timer = useRef<number | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const open = () => {
    onIntent?.();
    timer.current = window.setTimeout(() => {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return;
      const width = 280;
      const left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
      const below = r.bottom + 230 < window.innerHeight;
      setPos({ left, top: below ? r.bottom + 6 : r.top - 236 });
    }, 350);
  };
  const close = () => {
    if (timer.current) window.clearTimeout(timer.current);
    setPos(null);
  };
  useEffect(() => close, []);

  return (
    <span
      ref={ref}
      onMouseEnter={open}
      onMouseLeave={close}
      className="hover-preview-anchor"
    >
      {children}
      {pos &&
        createPortal(
          <div
            className="hover-preview"
            style={{ left: pos.left, top: pos.top }}
          >
            {preview()}
          </div>,
          document.body,
        )}
    </span>
  );
}

/** Hover card with the area's border; starts fetching it the moment the pointer arrives. */
export function AreaHover({
  area,
  children,
}: {
  area: AreaRef;
  children: ReactNode;
}) {
  return (
    <HoverPreview
      onIntent={() => void loadBoundary(area)}
      preview={() => <AreaPreview area={area} />}
    >
      {children}
    </HoverPreview>
  );
}
