import { useState } from "react";
import { api } from "../api";
import { useSession } from "../App";
import type { User } from "../types";

export default function Settings() {
  const { user, config, setUser } = useSession();
  const [email, setEmail] = useState(user.email ?? "");
  const [code, setCode] = useState("");
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

  const pendingVerification = !!user.email && !user.email_verified;

  return (
    <div className="settings">
      <h1>Settings</h1>

      <section className="card">
        <h2>Telegram</h2>
        <p>
          Signed in as <b>{user.display_name}</b>
          {user.username && <> (@{user.username})</>}.
        </p>
        <label className="inline">
          <input
            type="checkbox"
            checked={user.notify_telegram}
            disabled={busy || !config.telegram_bot}
            onChange={(e) => patch({ notify_telegram: e.target.checked })}
          />{" "}
          Send notifications to Telegram
        </label>
        {user.telegram_blocked && (
          <p className="banner warn">
            The bot can't reach you. Open{" "}
            <a href={`https://t.me/${config.telegram_bot}`} target="_blank" rel="noreferrer">
              @{config.telegram_bot}
            </a>{" "}
            and press Start.
          </p>
        )}
      </section>

      <section className="card">
        <h2>Email</h2>
        {!config.email_enabled ? (
          <p className="muted">Email delivery is not configured on this server.</p>
        ) : (
          <>
            {user.email_verified ? (
              <>
                <p>
                  Verified address: <b>{user.email}</b>
                </p>
                <label className="inline">
                  <input
                    type="checkbox"
                    checked={user.notify_email}
                    disabled={busy}
                    onChange={(e) => patch({ notify_email: e.target.checked })}
                  />{" "}
                  Send notifications by email
                </label>
                <div className="row">
                  <button
                    disabled={busy}
                    onClick={() => run(async () => setUser(await api<User>("/api/me/email", { method: "DELETE" })))}
                  >
                    Remove email
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="row">
                  <input
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  <button
                    disabled={busy || !email}
                    onClick={() =>
                      run(async () => {
                        setUser(await api<User>("/api/me/email", { method: "POST", json: { email } }));
                        setMsg("We sent a 6-digit code to your email.");
                      })
                    }
                  >
                    {pendingVerification ? "Resend code" : "Send code"}
                  </button>
                </div>
                {pendingVerification && (
                  <div className="row">
                    <input placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
                    <button
                      className="primary"
                      disabled={busy || code.length < 6}
                      onClick={() =>
                        run(async () => {
                          setUser(await api<User>("/api/me/email/verify", { method: "POST", json: { code } }));
                          setMsg("Email verified, email notifications enabled.");
                        })
                      }
                    >
                      Verify
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h2>Test</h2>
        <button
          disabled={busy}
          onClick={() =>
            run(async () => {
              const res = await api<{ channel: string; status: string; error: string | null }[]>(
                "/api/me/test-notification",
                { method: "POST" },
              );
              setMsg(res.map((r) => `${r.channel}: ${r.status}${r.error ? ` (${r.error})` : ""}`).join(" · "));
            })
          }
        >
          Send test notification
        </button>
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
