import { useEffect } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { pinIcon } from "./mapIcons";
import type { Criteria } from "../types";

const STOCKHOLM: [number, number] = [59.3293, 18.0686];

function ClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

function Recenter({ to }: { to: [number, number] | null }) {
  const map = useMap();
  const key = to?.join(",");
  useEffect(() => {
    if (to) map.setView(to, map.getZoom());
  }, [key, map]);
  return null;
}

export default function RadiusPicker({
  value,
  onChange,
  fallbackCenter,
}: {
  value: Criteria;
  onChange: (c: Criteria) => void;
  fallbackCenter?: [number, number] | null;
}) {
  const center: [number, number] | null =
    value.center_lat != null && value.center_lon != null ? [value.center_lat, value.center_lon] : null;
  const radius = value.radius_km ?? 2;
  return (
    <div className="radius-picker">
      <div className="row">
        <span className="muted small">Click the map to set the center.</span>
        <label className="inline">
          Radius
          <input
            type="number"
            min={0.2}
            max={200}
            step={0.5}
            value={radius}
            onChange={(e) => onChange({ ...value, radius_km: Number(e.target.value) || null })}
          />
          km
        </label>
      </div>
      <MapContainer center={center ?? fallbackCenter ?? STOCKHOLM} zoom={12} className="map small-map">
        {!center && <Recenter to={fallbackCenter ?? null} />}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ClickHandler
          onPick={(lat, lon) =>
            onChange({ ...value, center_lat: +lat.toFixed(5), center_lon: +lon.toFixed(5), radius_km: radius })
          }
        />
        {center && (
          <>
            <Marker position={center} icon={pinIcon} />
            <Circle center={center} radius={radius * 1000} pathOptions={{ color: "#2563eb" }} />
          </>
        )}
      </MapContainer>
    </div>
  );
}
