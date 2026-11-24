import type { CSSProperties, ReactNode } from "react";
import { Building, Building2, House, Houses, LandPlot, TentTree, Tractor, Waves, type LucideIcon } from "lucide-react";

const TYPE_ICONS: Record<string, LucideIcon> = {
  APARTMENT: Building2,
  HOUSE: House,
  ROW_HOUSE: Houses,
  TWIN_HOUSE: Houses,
  LINKED_HOUSE: Houses,
  TERRACED_HOUSE: Houses,
  VACATION_HOUSE: TentTree,
  VACATION_HOME: TentTree,
  WINTERIZED_VACATION_HOME: TentTree,
  PLOT: LandPlot,
  HOMESTEAD: Tractor,
  ESTATE_WITHOUT_CULTIVATION: Tractor,
  FORESTING_ESTATE: Tractor,
};

export function TypeIcon({ symbol, size = 14 }: { symbol: string | null; size?: number }) {
  const Icon = (symbol && TYPE_ICONS[symbol]) || Building;
  return <Icon size={size} aria-hidden />;
}

export function TypeBadge({ symbol, name }: { symbol: string | null; name: string | null }) {
  if (!symbol && !name) return null;
  return (
    <span className="type-badge" title={name ?? undefined}>
      <TypeIcon symbol={symbol} /> {name}
    </span>
  );
}

// Each room count gets its own colour (cool hues, so they never read as the green-red price
// scale); 6+ rooms share one.
const ROOM_HUES = [195, 220, 250, 280, 310, 335];

// Sequential scales (cheap = green, expensive = red). Band edges follow the spread of
// Stockholm-area listings so each colour covers a meaningful share of them.
const SEQ_HUES = [145, 115, 85, 55, 35, 18, 0];
const SCALES = {
  price: { edges: [2_000_000, 2_750_000, 3_500_000, 4_500_000, 6_000_000, 9_000_000], label: "Price" },
  sqm: { edges: [45_000, 55_000, 65_000, 75_000, 90_000, 110_000], label: "Price per m²" },
  fee: { edges: [2_500, 3_200, 3_800, 4_500, 5_300, 6_500], label: "Monthly fee" },
} as const;
export type Scale = keyof typeof SCALES;

const short = (v: number) =>
  v >= 1_000_000 ? `${+(v / 1_000_000).toFixed(2)} Mkr` : `${+(v / 1000).toFixed(1)}k`;

function band(scale: Scale, v: number): { hue: number; title: string } {
  const { edges, label } = SCALES[scale];
  const i = edges.findIndex((e) => v < e);
  const idx = i === -1 ? edges.length : i;
  const range =
    idx === 0 ? `under ${short(edges[0])}` : idx === edges.length ? `${short(edges[idx - 1])}+` : `${short(edges[idx - 1])}–${short(edges[idx])}`;
  return { hue: SEQ_HUES[idx], title: `${label}: ${range} (band ${idx + 1} of ${SEQ_HUES.length})` };
}

const hueStyle = (hue: number) => ({ "--h": hue }) as CSSProperties;

export function RoomsChip({ rooms, children }: { rooms: number; children: ReactNode }) {
  const hue = ROOM_HUES[Math.min(Math.max(Math.floor(rooms), 1), ROOM_HUES.length) - 1];
  return (
    <span className="grade" style={hueStyle(hue)}>
      {children}
    </span>
  );
}

export function GradeChip({ scale, value, children, big }: { scale: Scale; value: number | null; children: ReactNode; big?: boolean }) {
  if (value == null) return <span className={`grade neutral ${big ? "big" : ""}`}>{children}</span>;
  const { hue, title } = band(scale, value);
  return (
    <span className={`grade ${big ? "big" : ""}`} style={hueStyle(hue)} title={title}>
      {children}
    </span>
  );
}

export function PlainChip({ children }: { children: ReactNode }) {
  return <span className="grade neutral">{children}</span>;
}

export const NEAR_WATER_M = 500;

const metres = (m: number) => (m >= 1000 ? `${+(m / 1000).toFixed(1)} km` : `${m} m`);

/** "Close to water" badge for listings within NEAR_WATER_M of a lake or the sea. */
export function WaterBadge({ water, coast }: { water: number | null; coast?: number | null }) {
  if (water == null || water > NEAR_WATER_M) return null;
  const sea = coast != null && coast <= water + 50;
  return (
    <span className="badge water" title={`${sea ? "Sea" : "Water"} ${metres(water)} away (Hemnet)`}>
      <Waves size={12} /> {water <= 100 ? "By the water" : "Near water"} · {metres(water)}
    </span>
  );
}

export const distance = (m: number | null) => (m == null ? null : metres(m));
