import { memo, useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import L from "leaflet";
import type { MapPoint } from "../types";
import { mkr, num } from "../format";
import { GradeChip, RoomsChip } from "./Grading";

const COLORS: Record<string, string> = { active: "#2563eb", sold: "#dc2626", removed: "#6b7280" };
const HIGHLIGHT = "#f97316";

function FitBounds({ points, fitKey }: { points: MapPoint[]; fitKey: string }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lon] as [number, number])), {
      padding: [30, 30],
      maxZoom: 15,
    });
    // Refit only when the set of points changes, not on every render.
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
      <span className="facts">
        <GradeChip scale="price" value={p.asking_price}>{mkr(p.asking_price)}</GradeChip>
        {p.rooms != null && <RoomsChip rooms={p.rooms}>{num(p.rooms)} rum</RoomsChip>}
        {p.living_area != null && <span className="grade neutral">{num(p.living_area)} m²</span>}
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
          pathOptions={{ color: COLORS[p.status] ?? COLORS.active, fillOpacity: 0.75, weight: 1 }}
          eventHandlers={onHover ? { mouseover: () => onHover(p.id), mouseout: () => onHover(null) } : undefined}
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

export default function ListingsMap({ points, highlight, onHover, className = "big-map" }: Props) {
  const fitKey = points.map((p) => p.id).join(",");

  return (
    <MapContainer center={[59.33, 18.07]} zoom={11} className={`map ${className}`} preferCanvas>
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
            pathOptions={{ color: "#fff", weight: 3, fillColor: HIGHLIGHT, fillOpacity: 1 }}
          >
            <Tooltip permanent direction="top" offset={[0, -10]} className="price-tip">
              {mkr(highlight.asking_price)}
            </Tooltip>
          </CircleMarker>
        </>
      )}
    </MapContainer>
  );
}
