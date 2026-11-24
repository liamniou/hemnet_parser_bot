import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { NotificationItem } from "../types";
import { dateTime } from "../format";

const KIND: Record<string, string> = { new: "🏠 New", price_drop: "📉 Price drop", sold: "🔨 Sold", test: "✅ Test" };

export default function Notifications() {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  useEffect(() => {
    api<NotificationItem[]>("/api/me/notifications").then(setItems);
  }, []);

  return (
    <div>
      <h1>Notifications</h1>
      {items && items.length === 0 && <div className="card empty">Nothing sent yet.</div>}
      {items && items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Event</th>
              <th>Listing</th>
              <th>Search</th>
              <th>Channel</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((n) => (
              <tr key={n.id}>
                <td className="nowrap">{dateTime(n.created_at)}</td>
                <td className="nowrap">{KIND[n.kind] ?? n.kind}</td>
                <td>{n.listing_id ? <Link to={`/listings/${n.listing_id}`}>{n.listing_title}</Link> : "–"}</td>
                <td>{n.search_name ?? "–"}</td>
                <td>{n.channel}</td>
                <td title={n.error ?? ""} className={n.status === "failed" ? "error" : ""}>
                  {n.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
