import { Link } from "react-router-dom";
import { Eye, EyeOff, Heart, TrendingDown } from "lucide-react";
import CardSlider from "./CardSlider";
import type { ListingCard as Card } from "../types";
import { date, kr, num, title } from "../format";
import { GradeChip, PlainChip, RoomsChip, TypeBadge, WaterBadge } from "./Grading";

export function StatusBadge({ l }: { l: Pick<Card, "status" | "upcoming" | "new_construction"> }) {
  if (l.status === "sold") return <span className="badge sold">Sold</span>;
  if (l.status === "removed") return <span className="badge removed">Removed</span>;
  if (l.upcoming) return <span className="badge">Coming soon</span>;
  if (l.new_construction) return <span className="badge">New construction</span>;
  return null;
}

interface Props {
  l: Card;
  onFavorite?: (l: Card) => void;
  onHide?: (l: Card) => void;
  onHover?: (id: string | null) => void;
  highlighted?: boolean;
}

export default function ListingCardView({ l, onFavorite, onHide, onHover, highlighted }: Props) {
  return (
    <Link
      to={`/listings/${l.id}`}
      className={`listing-card ${l.hidden ? "dim" : ""} ${highlighted ? "highlighted" : ""}`}
      onMouseEnter={onHover ? () => onHover(l.id) : undefined}
      onMouseLeave={onHover ? () => onHover(null) : undefined}
    >
      <div className="cover">
        <CardSlider photos={l.photos?.length ? l.photos : l.cover ? [l.cover] : []} />
        <div className="badges">
          <StatusBadge l={l} />
          {l.price_dropped && (
            <span className="badge drop">
              <TrendingDown size={12} /> Price drop
            </span>
          )}
        </div>
        <div className="card-actions">
          {onHide && (
            <button
              className="card-action hide"
              title={l.hidden ? "Unhide" : "Hide (only for you)"}
              aria-label={l.hidden ? "Unhide" : "Hide"}
              onClick={(e) => {
                e.preventDefault();
                onHide(l);
              }}
            >
              {l.hidden ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
          )}
          {onFavorite && (
            <button
              className={`card-action fav ${l.favorite ? "on" : ""}`}
              title={l.favorite ? "Remove from saved" : "Save"}
              aria-label={l.favorite ? "Remove from saved" : "Save"}
              onClick={(e) => {
                e.preventDefault();
                onFavorite(l);
              }}
            >
              <Heart size={18} fill={l.favorite ? "currentColor" : "none"} />
            </button>
          )}
        </div>
        <div className="cover-type">
          <TypeBadge symbol={l.housing_form} name={l.housing_form_name} />
          <WaterBadge water={l.water_distance} coast={l.coastline_distance} />
        </div>
      </div>
      <div className="body">
        <div className="price">
          {l.status === "sold" && l.sold_price ? (
            <>
              <GradeChip scale="price" value={l.sold_price} big>
                {kr(l.sold_price)}
              </GradeChip>{" "}
              <small className="muted">{l.sold_price_change}</small>
            </>
          ) : (
            <GradeChip scale="price" value={l.asking_price} big>
              {l.asking_price_text || kr(l.asking_price)}
            </GradeChip>
          )}
        </div>
        <div className="addr">{title(l)}</div>
        <div className="facts">
          {l.rooms != null && <RoomsChip rooms={l.rooms}>{num(l.rooms)} rum</RoomsChip>}
          {l.living_area != null && (
            <PlainChip>
              {num(l.living_area)}
              {l.supplemental_area ? `+${num(l.supplemental_area)}` : ""} m²
            </PlainChip>
          )}
          {l.fee != null && (
            <GradeChip scale="fee" value={l.fee}>
              {kr(l.fee, " kr/mån")}
            </GradeChip>
          )}
          {l.sqm_price != null && (
            <GradeChip scale="sqm" value={l.sqm_price}>
              {kr(l.sqm_price, " kr/m²")}
            </GradeChip>
          )}
        </div>
        <div className="meta muted small">
          Published {date(l.published_at ?? l.first_seen_at)}
          {l.status === "sold" && l.sold_at && <> · sold {date(l.sold_at)}</>}
        </div>
      </div>
    </Link>
  );
}
