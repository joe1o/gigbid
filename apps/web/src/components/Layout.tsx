// Layout.tsx - the app frame: navigation, theme toggle, sign out, and the
// "marketplace unavailable" banner (polled every 15 s from /api/health).
import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, unwrap } from "../lib/api/client";
import { useLoad } from "../lib/hooks";

const LINKS = [
  ["/inbox", "Inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"],
  ["/analytics", "Analytics"], ["/settings", "Settings"],
] as const;

export function useTheme() {
  const [theme, setTheme] = useState<string>(() => localStorage.getItem("theme") ?? "");
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
  const dark = theme ? theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  return { dark, toggle: () => setTheme(dark ? "light" : "dark") };
}

export default function Layout() {
  const nav = useNavigate();
  const { dark, toggle } = useTheme();
  const health = useLoad(async () => unwrap(await api.GET("/api/health")), [], 15000, () => true);
  const down = health.data?.marketplace === "down";

  async function signOut() {
    await api.POST("/api/auth/logout");
    nav("/login");
  }

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand"><span className="brand-mark">G</span> GigBid</div>
        <nav className="nav" aria-label="Main">
          {LINKS.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        </nav>
        <div className="side-foot">
          <button className="btn small ghost" onClick={toggle} aria-label="Toggle dark mode">{dark ? "Light mode" : "Dark mode"}</button>
          <button className="btn small ghost" onClick={signOut}>Sign out</button>
        </div>
      </aside>
      <div>
        {down && (
          <div className="banner" role="alert" data-testid="degraded-banner">
            <strong>Marketplace unavailable.</strong> GigBid can't reach the marketplace right now.
            {health.data?.queued_jobs ? ` ${health.data.queued_jobs} job(s) are queued` : " Work is queued"} and will resume
            automatically when it's back. Nothing is lost.
          </div>
        )}
        <main className="main"><Outlet /></main>
      </div>
    </div>
  );
}
