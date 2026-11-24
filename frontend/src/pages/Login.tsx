import { useEffect, useState } from "react";
import { Mail } from "lucide-react";
import { api } from "../api";
import type { AppConfig, User } from "../types";

interface Props {
  config: AppConfig;
  onLogin: (u: User) => void;
}

export default function Login({ config, onLogin }: Props) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finish = (u: User) => {
    window.history.replaceState(null, "", "/");
    onLogin(u);
  };

  // Sign-in link from the email: /login?token=...
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) return;
    setBusy(true);
    api<{ user: User }>("/api/auth/email/link", { method: "POST", json: { token } })
      .then((r) => finish(r.user))
      .catch((e) => {
        window.history.replaceState(null, "", "/");
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setBusy(false));
  }, []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sendCode = () =>
    run(async () => {
      await api("/api/auth/email", { method: "POST", json: { email } });
      setSent(true);
      setCode("");
    });

  const verify = () =>
    run(async () => {
      const r = await api<{ user: User }>("/api/auth/email/verify", { method: "POST", json: { email, code } });
      finish(r.user);
    });

  const devLogin = () =>
    run(async () => finish(await api<User>(`/api/auth/dev-login?email=${encodeURIComponent(email)}`, { method: "POST" })));

  return (
    <div className="login">
      <div className="card login-card">
        <h1>🏠 Hemnet Watch</h1>
        <p className="muted">
          Archive of Hemnet listings with personal email alerts for new ads, price drops and final sale prices.
        </p>
        {!config.email_enabled && !config.dev_login ? (
          <p className="banner warn">Email is not configured on the server (SMTP_HOST / SMTP_FROM).</p>
        ) : !sent ? (
          <form
            className="login-form"
            onSubmit={(e) => {
              e.preventDefault();
              sendCode();
            }}
          >
            <input
              type="email"
              autoComplete="email"
              autoFocus
              required
              placeholder="you@example.com"
              aria-label="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {config.email_enabled && (
              <button className="primary big" disabled={busy || !email}>
                <Mail size={18} /> Email me a sign-in code
              </button>
            )}
            {config.dev_login && (
              <button type="button" disabled={busy || !email} onClick={devLogin}>
                Dev login
              </button>
            )}
          </form>
        ) : (
          <form
            className="login-form"
            onSubmit={(e) => {
              e.preventDefault();
              verify();
            }}
          >
            <p>
              We sent a 6-digit code to <b>{email}</b>. Enter it below, or click the link in the email.
            </p>
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              maxLength={6}
              placeholder="123456"
              aria-label="Code"
              className="code-input"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
            <button className="primary big" disabled={busy || code.length !== 6}>
              Sign in
            </button>
            <div className="row center-row">
              <button type="button" className="link" onClick={() => setSent(false)}>
                Use another email
              </button>
              <button type="button" className="link" disabled={busy} onClick={sendCode}>
                Resend code
              </button>
            </div>
          </form>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
