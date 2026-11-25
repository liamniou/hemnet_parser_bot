import { memo, useEffect } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import { Link } from "react-router-dom";
import L from "leaflet";
import type { MapPoint } from "../types";
import { mkr, num } from "../format";
import {
  GradeChip,
  RoomsChip,
  TypeBadge,
  typeColor,
  typeGroup,
} from "./Grading";

const HIGHLIGHT = "#f97316";

// Frame the central 98% of points so a few mis-geocoded listings (e.g. coordinates in another
// county) don't zoom the map out to all of Sweden. Outliers are still drawn.
function framingBounds(points: MapPoint[]) {
  if (points.length < 50)
    return L.latLngBounds(
      points.map((p) => [p.lat, p.lon] as [number, number]),
    );
  const lats = points.map((p) => p.lat).sort((a, b) => a - b);
  const lons = points.map((p) => p.lon).sort((a, b) => a - b);
  const q = (arr: number[], f: number) =>
    arr[
      Math.min(arr.length - 1, Math.max(0, Math.round(f * (arr.length - 1))))
    ];
  return L.latLngBounds(
    [q(lats, 0.01), q(lons, 0.01)],
    [q(lats, 0.99), q(lons, 0.99)],
  );
}

function FitBounds({ points, fitKey }: { points: MapPoint[]; fitKey: string }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    map.fitBounds(framingBounds(points), { padding: [30, 30], maxZoom: 15 });
  }, [fitKey, map]);
  return null;
}

function KeepInView({ point }: { point: MapPoint | null }) {
  const map = useMap();
  useEffect(() => {
    if (point && !map.getBounds().pad(-0.05).contains([point.lat, point.lon])) {
      map.panTo([point.lat, point.lon], { animate: true });
    }
  }, [point, map]);
  return null;
}

function PointPopup({ p }: { p: MapPoint }) {
  return (
    <Popup>
      <Link to={`/listings/${p.id}`}>
        <b>{p.street_address}</b>
      </Link>
      <div>
        <TypeBadge symbol={p.housing_form} name={p.housing_form_name} />
        {p.status !== "active" && (
          <span className="muted small"> · {p.status}</span>
        )}
      </div>
      <span className="facts">
        <GradeChip scale="price" value={p.asking_price}>
          {mkr(p.asking_price)}
        </GradeChip>
        {p.rooms != null && (
          <RoomsChip rooms={p.rooms}>{num(p.rooms)} rum</RoomsChip>
        )}
        {p.living_area != null && (
          <span className="grade neutral">{num(p.living_area)} m²</span>
        )}
      </span>
    </Popup>
  );
}

// Memoised so hovering a card re-renders only the highlight marker, not every dot.
const Markers = memo(function Markers({
  points,
  onHover,
}: {
  points: MapPoint[];
  onHover?: (id: string | null) => void;
}) {
  return (
    <>
      {points.map((p) => (
        <CircleMarker
          key={p.id}
          center={[p.lat, p.lon]}
          radius={6}
          pathOptions={
            p.status === "active"
              ? {
                  color: "#fff",
                  weight: 1,
                  fillColor: typeColor(p.housing_form),
                  fillOpacity: 0.9,
                }
              : // Sold/removed: hollow ring in the type colour.
                {
                  color: typeColor(p.housing_form),
                  weight: 2,
                  fillColor: "#fff",
                  fillOpacity: 0.6,
                }
          }
          eventHandlers={
            onHover
              ? {
                  mouseover: () => onHover(p.id),
                  mouseout: () => onHover(null),
                }
              : undefined
          }
        >
          <PointPopup p={p} />
        </CircleMarker>
      ))}
    </>
  );
});

interface Props {
  points: MapPoint[];
  highlight?: MapPoint | null;
  onHover?: (id: string | null) => void;
  className?: string;
}

function Legend({ points }: { points: MapPoint[] }) {
  const groups = new Map<string, { label: string; color: string; n: number }>();
  for (const p of points) {
    const g = typeGroup(p.housing_form);
    const cur = groups.get(g.key) ?? { label: g.label, color: g.color, n: 0 };
    cur.n += 1;
    groups.set(g.key, cur);
  }
  const inactive = points.some((p) => p.status !== "active");
  if (groups.size < 2 && !inactive) return null;
  return (
    <div className="map-legend">
      {[...groups.values()].map((g) => (
        <span key={g.label}>
          <i style={{ background: g.color }} /> {g.label} <small>{g.n}</small>
        </span>
      ))}
      {inactive && (
        <span>
          <i className="ring" /> Sold / removed
        </span>
      )}
    </div>
  );
}

export default function ListingsMap({
  points,
  highlight,
  onHover,
  className = "big-map",
}: Props) {
  const fitKey = points.map((p) => p.id).join(",");

  return (
    <div className="map-wrap">
      <Legend points={points} />
      <MapContainer
        center={[59.33, 18.07]}
        zoom={11}
        className={`map ${className}`}
        preferCanvas
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={points} fitKey={fitKey} />
        <Markers points={points} onHover={onHover} />
        {highlight && (
          <>
            <KeepInView point={highlight} />
            <CircleMarker
              key={`hl-${highlight.id}`}
              center={[highlight.lat, highlight.lon]}
              radius={10}
              interactive={false}
              pathOptions={{
                color: "#fff",
                weight: 3,
                fillColor: HIGHLIGHT,
                fillOpacity: 1,
              }}
            >
              <Tooltip
                permanent
                direction="top"
                offset={[0, -10]}
                className="price-tip"
              >
                {mkr(highlight.asking_price)}
              </Tooltip>
            </CircleMarker>
          </>
        )}
      </MapContainer>
    </div>
  );
}
