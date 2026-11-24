import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, EyeOff, ExternalLink, Heart } from "lucide-react";
import { MapContainer, Marker, TileLayer } from "react-leaflet";
import { api } from "../api";
import { StatusBadge } from "../components/ListingCard";
import { GradeChip, RoomsChip, TypeBadge, WaterBadge, distance } from "../components/Grading";
import { pinIcon } from "../components/mapIcons";
import type { ListingDetail as Detail } from "../types";
import { date, dateTime, kr, num, title } from "../format";

export default function ListingDetail() {
  const { id } = useParams();
  const [l, setL] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [note, setNote] = useState("");
  const [noteSaved, setNoteSaved] = useState(true);

  useEffect(() => {
    setL(null);
    setIdx(0);
    api<Detail>(`/api/listings/${id}`)
      .then((d) => {
        setL(d);
        setNote(d.note ?? "");
      })
      .catch((e) => setError(String(e)));
  }, [id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!l || (e.target as HTMLElement).tagName === "TEXTAREA") return;
      if (e.key === "ArrowRight") setIdx((i) => (i + 1) % l.gallery.length);
      if (e.key === "ArrowLeft") setIdx((i) => (i - 1 + l.gallery.length) % l.gallery.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [l]);

  if (error) return <p className="error">{error}</p>;
  if (!l) return <p className="muted">Loading…</p>;

  const setState = async (patch: { favorite?: boolean; hidden?: boolean; note?: string }) => {
    const res = await api<{ favorite: boolean; hidden: boolean; note: string | null }>(
      `/api/listings/${l.id}/state`,
      { method: "PUT", json: patch },
    );
    setL({ ...l, ...res });
    if (patch.note !== undefined) setNoteSaved(true);
  };

  const img = l.gallery[idx];
  const facts: [string, React.ReactNode][] = [
    ["Asking price", <GradeChip scale="price" value={l.asking_price}>{l.asking_price_text || kr(l.asking_price)}</GradeChip>],
    ["Rooms", l.rooms != null ? <RoomsChip rooms={l.rooms}>{num(l.rooms)} rum</RoomsChip> : null],
    ["Living area", l.living_area ? `${num(l.living_area)} m²` : "–"],
    ["Supplemental area", l.supplemental_area ? `${num(l.supplemental_area)} m²` : null],
    ["Land area", l.land_area ? `${num(l.land_area)} m²` : null],
    ["Fee", l.fee != null ? <GradeChip scale="fee" value={l.fee}>{kr(l.fee, " kr/mån")}</GradeChip> : null],
    ["Running costs", l.running_costs != null ? kr(l.running_costs, " kr/år") : null],
    ["Price / m²", l.sqm_price != null ? <GradeChip scale="sqm" value={l.sqm_price}>{kr(l.sqm_price, " kr/m²")}</GradeChip> : null],
    ["Floor", l.floor],
    ["Year built", l.year_built],
    ["Balcony", l.has_balcony == null ? null : l.has_balcony ? "Yes" : "No"],
    ["Elevator", l.has_elevator == null ? null : l.has_elevator ? "Yes" : "No"],
    ["Nearest water", distance(l.water_distance)],
    ["Distance to the sea", distance(l.coastline_distance)],
    ["Energy class", l.energy_class],
    ["Association", l.brf_name],
    ["Broker", [l.broker_name, l.broker_agency].filter(Boolean).join(", ")],
    ["Districts", l.districts.join(", ")],
    ["Published", date(l.published_at)],
    ["First seen", dateTime(l.first_seen_at)],
    ["Last seen", dateTime(l.last_seen_at)],
    ["Hemnet ID", l.id],
  ];

  return (
    <div className="detail">
      <Link to="/" className="back">
        <ArrowLeft size={16} /> Back to listings
      </Link>
      <div className="detail-head">
        <div>
          <h1>
            {title(l)} <StatusBadge l={l} />
          </h1>
          <div className="row">
            <TypeBadge symbol={l.housing_form} name={[l.housing_form_name, l.tenure].filter(Boolean).join(" · ")} />
            <WaterBadge water={l.water_distance} coast={l.coastline_distance} />
          </div>
          <div className="price big">
            {l.status === "sold" ? (
              <>
                Sold for{" "}
                <GradeChip scale="price" value={l.sold_price} big>
                  {l.sold_price_text || kr(l.sold_price)}
                </GradeChip>{" "}
                <span className="muted">
                  {l.sold_price_change} · {date(l.sold_at)}
                </span>
              </>
            ) : (
              <GradeChip scale="price" value={l.asking_price} big>
                {l.asking_price_text || kr(l.asking_price)}
              </GradeChip>
            )}
          </div>
        </div>
        <div className="row">
          <button className={l.favorite ? "on" : ""} onClick={() => setState({ favorite: !l.favorite })}>
            <Heart size={16} fill={l.favorite ? "currentColor" : "none"} /> {l.favorite ? "Saved" : "Save"}
          </button>
          <button className={l.hidden ? "on" : ""} onClick={() => setState({ hidden: !l.hidden })}>
            <EyeOff size={16} /> {l.hidden ? "Hidden" : "Hide"}
          </button>
          <a className="button" href={l.url} target="_blank" rel="noreferrer">
            <ExternalLink size={16} /> Hemnet
          </a>
        </div>
      </div>

      {l.gallery.length > 0 && (
        <div className="gallery">
          <div className="main-img">
            <img src={img.url} alt="" />
            {l.gallery.length > 1 && (
              <>
                <button className="nav prev" onClick={() => setIdx((idx - 1 + l.gallery.length) % l.gallery.length)}>
                  <ChevronLeft />
                </button>
                <button className="nav next" onClick={() => setIdx((idx + 1) % l.gallery.length)}>
                  <ChevronRight />
                </button>
                <span className="counter">
                  {idx + 1} / {l.gallery.length}
                </span>
              </>
            )}
          </div>
          <div className="thumbs">
            {l.gallery.map((g, i) => (
              <img key={g.url} src={g.url} alt="" loading="lazy" className={i === idx ? "on" : ""} onClick={() => setIdx(i)} />
            ))}
          </div>
          {l.images_status !== "done" && (
            <p className="muted small">
              {l.images_status === "pending"
                ? "Images are not archived yet; showing Hemnet previews."
                : "Image archiving failed; showing Hemnet previews."}
            </p>
          )}
        </div>
      )}

      <div className="detail-cols">
        <div>
          <table className="facts-table">
            <tbody>
              {facts
                .filter(([, v]) => v != null && v !== "" && v !== "–")
                .map(([k, v]) => (
                  <tr key={k}>
                    <th>{k}</th>
                    <td>{v}</td>
                  </tr>
                ))}
            </tbody>
          </table>

          {l.price_history.length > 0 && (
            <>
              <h3>Price history</h3>
              <table className="facts-table">
                <tbody>
                  {l.price_history.map((p) => (
                    <tr key={p.changed_at}>
                      <th>{date(p.changed_at)}</th>
                      <td>
                        {kr(p.old_price)} → <b>{kr(p.new_price)}</b>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h3>My notes</h3>
          <textarea
            rows={4}
            value={note}
            placeholder="Viewing notes, questions for the broker…"
            onChange={(e) => {
              setNote(e.target.value);
              setNoteSaved(false);
            }}
          />
          <button disabled={noteSaved} onClick={() => setState({ note })}>
            {noteSaved ? "Saved" : "Save note"}
          </button>
        </div>
        <div>
          {l.lat != null && l.lon != null && (
            <MapContainer center={[l.lat, l.lon]} zoom={14} className="map small-map" scrollWheelZoom={false}>
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <Marker position={[l.lat, l.lon]} icon={pinIcon} />
            </MapContainer>
          )}
          {l.description && (
            <>
              <h3>Description</h3>
              <p className="description">{l.description}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
