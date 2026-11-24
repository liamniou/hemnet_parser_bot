import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import { Link } from "react-router-dom";
import L from "leaflet";
import type { MapPoint } from "../types";
import { mkr, num } from "../format";
import { GradeChip, RoomsChip } from "./Grading";

const COLORS: Record<string, string> = { active: "#2563eb", sold: "#dc2626", removed: "#6b7280" };

function FitBounds({ points }: { points: MapPoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lon] as [number, number])), {
      padding: [30, 30],
      maxZoom: 15,
    });
  }, [points, map]);
  return null;
}

export default function ListingsMap({ points }: { points: MapPoint[] }) {
  return (
    <MapContainer center={[59.33, 18.07]} zoom={11} className="map big-map" preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds points={points} />
      {points.map((p) => (
        <CircleMarker
          key={p.id}
          center={[p.lat, p.lon]}
          radius={6}
          pathOptions={{ color: COLORS[p.status] ?? "#2563eb", fillOpacity: 0.7, weight: 1 }}
        >
          <Popup>
            <Link to={`/listings/${p.id}`}>
              <b>{p.street_address}</b>
            </Link>
            <br />
            <span className="facts">
              <GradeChip scale="price" value={p.asking_price}>{mkr(p.asking_price)}</GradeChip>
              {p.rooms != null && <RoomsChip rooms={p.rooms}>{num(p.rooms)} rum</RoomsChip>}
              {p.living_area != null && <span className="grade neutral">{num(p.living_area)} m²</span>}
            </span>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
