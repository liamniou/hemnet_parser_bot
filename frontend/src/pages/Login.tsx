import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { api, ApiError } from "../api";
import type { AppConfig, User } from "../types";

interface Props {
  config: AppConfig;
  onLogin: (u: User) => void;
}

export default function Login({ config, onLogin }: Props) {
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devId, setDevId] = useState("1");
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  const start = async () => {
    setError(null);
    const tab = window.open("about:blank", "_blank");
    try {
      const res = await api<{ token: string; url: string }>("/api/auth/telegram", { method: "POST" });
      setLink(res.url);
      if (tab) {
        tab.opener = null;
        tab.location.href = res.url;
      }
      if (timer.current) window.clearInterval(timer.current);
      timer.current = window.setInterval(async () => {
        try {
          const r = await api<{ status: string; user?: User }>(`/api/auth/telegram/${res.token}`);
          if (r.status === "ok" && r.user) {
            window.clearInterval(timer.current!);
            onLogin(r.user);
          }
        } catch (e) {
          window.clearInterval(timer.current!);
          setLink(null);
          setError(e instanceof ApiError && e.status === 410 ? "Login link expired, try again." : String(e));
        }
      }, 2000);
    } catch (e) {
      tab?.close();
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const devLogin = async () => {
    try {
      onLogin(await api<User>(`/api/auth/dev-login?telegram_id=${devId}`, { method: "POST" }));
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="login">
      <div className="card login-card">
        <h1>🏠 Hemnet Watch</h1>
        <p className="muted">
          Archive of Hemnet listings with personal alerts for new ads, price drops and final sale
          prices, delivered to Telegram or email.
        </p>
        {config.telegram_bot ? (
          <>
            <button className="primary big" onClick={start}>
              <Send size={18} /> Log in with Telegram
            </button>
            {link && (
              <p className="hint">
                Waiting for confirmation in Telegram… Press <b>Start</b> and then <b>Confirm login</b>{" "}
                in the bot chat. If nothing opened, <a href={link} target="_blank" rel="noreferrer">open the bot</a>.
              </p>
            )}
          </>
        ) : (
          <p className="banner warn">Telegram bot is not configured on the server (TELEGRAM_BOT_TOKEN).</p>
        )}
        {config.dev_login && (
          <div className="row dev">
            <input value={devId} onChange={(e) => setDevId(e.target.value)} placeholder="telegram id" />
            <button onClick={devLogin}>Dev login</button>
          </div>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}
