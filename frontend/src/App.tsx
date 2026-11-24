import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Bell, Building2, Home, LogOut, Search, Settings as Cog, Shield } from "lucide-react";
import { api, setUnauthorizedHandler } from "./api";
import type { AppConfig, User } from "./types";
import Login from "./pages/Login";
import Listings from "./pages/Listings";
import ListingDetail from "./pages/ListingDetail";
import Searches from "./pages/Searches";
import Settings from "./pages/Settings";
import Notifications from "./pages/Notifications";
import Admin from "./pages/Admin";

interface Session {
  user: User;
  config: AppConfig;
  setUser: (u: User) => void;
}

const SessionCtx = createContext<Session | null>(null);

export const useSession = () => {
  const s = useContext(SessionCtx);
  if (!s) throw new Error("useSession outside provider");
  return s;
};

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const navigate = useNavigate();

  const loadUser = useCallback(() => {
    api<User>("/api/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    api<AppConfig>("/api/config").then(setConfig).catch(() =>
      setConfig({ email_enabled: false, dev_login: false }),
    );
    loadUser();
    setUnauthorizedHandler(() => setUser(null));
  }, [loadUser]);

  if (user === undefined || config === null) return <div className="center muted">Loading…</div>;
  if (user === null) return <Login config={config} onLogin={(u) => setUser(u)} />;

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    setUser(null);
    navigate("/");
  };

  return (
    <SessionCtx.Provider value={{ user, config, setUser }}>
      <div className="layout">
        <header className="topbar">
          <NavLink to="/" className="brand">
            <Home size={20} /> Hemnet Watch
          </NavLink>
          <nav>
            <NavLink to="/" end>
              <Building2 size={16} /> <span>Listings</span>
            </NavLink>
            <NavLink to="/searches">
              <Search size={16} /> <span>My searches</span>
            </NavLink>
            <NavLink to="/notifications">
              <Bell size={16} /> <span>Notifications</span>
            </NavLink>
            <NavLink to="/settings">
              <Cog size={16} /> <span>Settings</span>
            </NavLink>
            {user.is_admin && (
              <NavLink to="/admin">
                <Shield size={16} /> <span>Admin</span>
              </NavLink>
            )}
          </nav>
          <div className="who">
            <span className="muted">{user.display_name}</span>
            <button className="icon" title="Log out" onClick={logout}>
              <LogOut size={16} />
            </button>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Listings />} />
            <Route path="/listings/:id" element={<ListingDetail />} />
            <Route path="/searches" element={<Searches />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/settings" element={<Settings />} />
            {user.is_admin && <Route path="/admin/*" element={<Admin />} />}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </SessionCtx.Provider>
  );
}
