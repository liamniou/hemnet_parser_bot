import { Link } from "react-router-dom";
import { Heart, ImageIcon, TrendingDown } from "lucide-react";
import type { ListingCard as Card } from "../types";
import { date, kr, num, title } from "../format";

export function StatusBadge({ l }: { l: Pick<Card, "status" | "upcoming" | "new_construction"> }) {
  if (l.status === "sold") return <span className="badge sold">Sold</span>;
  if (l.status === "removed") return <span className="badge removed">Removed</span>;
  if (l.upcoming) return <span className="badge">Coming soon</span>;
  if (l.new_construction) return <span className="badge">New construction</span>;
  return null;
}

export default function ListingCardView({ l, onFavorite }: { l: Card; onFavorite?: (l: Card) => void }) {
  return (
    <Link to={`/listings/${l.id}`} className={`listing-card ${l.hidden ? "dim" : ""}`}>
      <div className="cover">
        {l.cover ? <img src={l.cover} alt="" loading="lazy" /> : <div className="noimg"><ImageIcon /></div>}
        <div className="badges">
          <StatusBadge l={l} />
          {l.price_dropped && (
            <span className="badge drop">
              <TrendingDown size={12} /> Price drop
            </span>
          )}
        </div>
        {onFavorite && (
          <button
            className={`fav ${l.favorite ? "on" : ""}`}
            title={l.favorite ? "Remove from saved" : "Save"}
            onClick={(e) => {
              e.preventDefault();
              onFavorite(l);
            }}
          >
            <Heart size={18} fill={l.favorite ? "currentColor" : "none"} />
          </button>
        )}
        {l.image_count > 1 && <span className="count">{l.image_count} 📷</span>}
      </div>
      <div className="body">
        <div className="price">
          {l.status === "sold" && l.sold_price ? (
            <>
              {kr(l.sold_price)} <small className="muted">{l.sold_price_change}</small>
            </>
          ) : (
            l.asking_price_text || kr(l.asking_price)
          )}
        </div>
        <div className="addr">{title(l)}</div>
        <div className="facts">
          {l.rooms != null && <span>{num(l.rooms)} rum</span>}
          {l.living_area != null && (
            <span>
              {num(l.living_area)}
              {l.supplemental_area ? `+${num(l.supplemental_area)}` : ""} m²
            </span>
          )}
          {l.fee != null && <span>{kr(l.fee, " kr/mån")}</span>}
          {l.sqm_price != null && <span>{kr(l.sqm_price, " kr/m²")}</span>}
        </div>
        <div className="meta muted small">
          {l.housing_form_name} · published {date(l.published_at ?? l.first_seen_at)}
          {l.status === "sold" && l.sold_at && <> · sold {date(l.sold_at)}</>}
        </div>
      </div>
    </Link>
  );
}
