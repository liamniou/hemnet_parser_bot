import { useState } from "react";
import { api } from "../api";
import { useSession } from "../App";
import type { User } from "../types";

export default function Settings() {
  const { user, config, setUser } = useSession();
  const [name, setName] = useState(user.name ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const patch = (body: Partial<User>) =>
    run(async () => setUser(await api<User>("/api/me", { method: "PATCH", json: body })));

  return (
    <div className="settings">
      <h1>Settings</h1>

      <section className="card">
        <h2>Account</h2>
        <p>
          Signed in as <b>{user.email}</b>.
        </p>
        <div className="row">
          <input placeholder="Display name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
          <button disabled={busy || name === (user.name ?? "")} onClick={() => patch({ name })}>
            Save name
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Email notifications</h2>
        {!config.email_enabled ? (
          <p className="muted">Email delivery is not configured on this server.</p>
        ) : (
          <>
            <label className="inline">
              <input
                type="checkbox"
                checked={user.notify_email}
                disabled={busy}
                onChange={(e) => patch({ notify_email: e.target.checked })}
              />{" "}
              Send alerts to {user.email}
            </label>
            <div className="row">
              <button
                disabled={busy || !user.notify_email}
                onClick={() =>
                  run(async () => {
                    const res = await api<{ status: string; error: string | null }[]>("/api/me/test-notification", {
                      method: "POST",
                    });
                    setMsg(res.map((r) => (r.status === "sent" ? "Test email sent." : `Failed: ${r.error}`)).join(" "));
                  })
                }
              >
                Send test email
              </button>
            </div>
          </>
        )}
      </section>

      {msg && <p className="banner">{msg}</p>}
      {error && <p className="error">{error}</p>}

      <section className="card danger-zone">
        <h2>Delete account</h2>
        <p className="muted">Removes your searches, saved listings and notification history.</p>
        <button
          className="danger"
          onClick={async () => {
            if (!window.confirm("Delete your account permanently?")) return;
            await api("/api/me", { method: "DELETE" });
            window.location.href = "/";
          }}
        >
          Delete my account
        </button>
      </section>
    </div>
  );
}
