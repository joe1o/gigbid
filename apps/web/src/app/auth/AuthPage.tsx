// AuthPage.tsx - sign in / create account (multi-user auth).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorBox } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";

export default function AuthPage() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { email, password };
      const user = unwrap(mode === "login" ? await api.POST("/api/auth/login", { body })
                                           : await api.POST("/api/auth/signup", { body }));
      nav(user.onboarded ? "/inbox" : "/onboarding");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth-side">
        <div className="brand" style={{ color: "rgb(245 245 245)" }}><span className="brand-mark">G</span> GigBid</div>
        <div>
          <h1>Find the work worth bidding on.</h1>
          <p style={{ color: "rgb(201 191 162)", maxWidth: 440 }}>
            A team of agents scouts jobs, flags scams, matches them to your real portfolio and drafts proposals
            where every claim has evidence. Nothing is sent until you approve it.
          </p>
        </div>
        <p className="small" style={{ color: "rgb(163 154 132)" }}>AI-4016 · runs on open models · GigSim marketplace</p>
      </section>
      <section className="auth-form">
        <form onSubmit={submit} aria-label={mode === "login" ? "Sign in" : "Create account"}>
          <h2 style={{ fontSize: 30, fontWeight: 300 }}>{mode === "login" ? "Sign in" : "Create your account"}</h2>
          <p className="muted small">
            {mode === "login" ? "New here? " : "Already have an account? "}
            <a href="#" onClick={(e) => { e.preventDefault(); setMode(mode === "login" ? "signup" : "login"); }}>
              {mode === "login" ? "Create one" : "Sign in"}
            </a>
          </p>
          <div className="field"><label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div className="field"><label htmlFor="password">Password {mode === "signup" && <span className="muted">(8+ characters)</span>}</label>
            <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"}
              required minLength={mode === "signup" ? 8 : 1} value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {error && <ErrorBox error={error} />}
          <button className="btn primary" style={{ width: "100%", marginTop: 12, padding: 11 }} disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </section>
    </div>
  );
}
