const nf = new Intl.NumberFormat("sv-SE");

export const kr = (v: number | null | undefined, suffix = " kr") =>
  v == null ? "–" : `${nf.format(v)}${suffix}`;

export const num = (v: number | null | undefined) =>
  v == null ? "–" : nf.format(v);

export const mkr = (v: number | null | undefined) =>
  v == null ? "–" : `${(v / 1_000_000).toLocaleString("sv-SE", { maximumFractionDigits: 2 })} Mkr`;

// Backend timestamps are naive UTC.
export const parseTs = (s: string | null | undefined) =>
  s ? new Date(s.endsWith("Z") ? s : `${s}Z`) : null;

export const date = (s: string | null | undefined) => {
  const d = parseTs(s);
  return d ? d.toLocaleDateString("sv-SE") : "–";
};

export const dateTime = (s: string | null | undefined) => {
  const d = parseTs(s);
  return d ? d.toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" }) : "–";
};

export const ago = (s: string | null | undefined) => {
  const d = parseTs(s);
  if (!d) return "never";
  const sec = Math.round((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
  return `${Math.round(sec / 86400)} d ago`;
};

export const bytes = (v: number | null | undefined) => {
  if (v == null) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let n = v;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
};

export const title = (l: { street_address: string | null; location_description: string | null }) =>
  [l.street_address, l.location_description].filter(Boolean).join(", ") || "Unknown address";
