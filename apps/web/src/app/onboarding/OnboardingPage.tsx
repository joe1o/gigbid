// OnboardingPage.tsx - 4 steps: choose a profile, connect a marketplace, review the portfolio,
// set rates / filters / weekly Connects budget. Then the first scout runs.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorBox } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";

const PERSONAS = [
  { id: "ml_engineer", name: "Sara Malik", role: "AI/ML engineer", cat: "ml", floor: 300, hourly: 35 },
  { id: "web_developer", name: "Omar Raza", role: "Full-stack web developer", cat: "web", floor: 400, hourly: 30 },
  { id: "data_analyst", name: "Hina Javed", role: "Data analyst", cat: "data", floor: 200, hourly: 25 },
] as const;
type PersonaId = (typeof PERSONAS)[number]["id"];

export default function OnboardingPage() {
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [persona, setPersona] = useState<PersonaId>("ml_engineer");
  const [own, setOwn] = useState(false);
  const [account, setAccount] = useState<PersonaId>("ml_engineer");
  const [floor, setFloor] = useState(300);
  const [hourly, setHourly] = useState(35);
  const [budget, setBudget] = useState(60);
  const [autonomy, setAutonomy] = useState<"manual" | "auto_skip">("manual");
  const [keywords, setKeywords] = useState("");
  const [upworkMsg, setUpworkMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const p = PERSONAS.find((x) => x.id === persona)!;

  function pick(id: PersonaId) {
    const x = PERSONAS.find((y) => y.id === id)!;
    setPersona(id); setAccount(id); setFloor(x.floor); setHourly(x.hourly);
  }

  async function tryUpwork() {
    const r = await api.POST("/api/accounts/upwork");
    setUpworkMsg((r.error as unknown as { detail?: string } | undefined)?.detail ?? "Connected");
  }

  async function finish() {
    setBusy(true);
    setError(null);
    try {
      unwrap(await api.POST("/api/onboarding", { body: {
        persona, own_profile: own, account, fixed_floor_usd: floor, hourly_floor_usd: hourly,
        connects_weekly_budget: budget, autonomy, searches: [{ query: keywords, category: p.cat }],
      } }));
      await api.POST("/api/scout");               // first scout runs straight away
      nav("/inbox");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="auth-form" style={{ minHeight: "100vh" }}>
      <div className="box" style={{ width: "min(620px, 100%)" }}>
        <div className="steps" aria-label={`Step ${step + 1} of 4`}>{[0, 1, 2, 3].map((i) => <span key={i} className={i <= step ? "on" : ""} />)}</div>
        <div className="eyebrow">Step {step + 1} of 4</div>

        {step === 0 && <section>
          <h1>Who are you bidding as?</h1>
          <p className="muted">Pick a ready-made freelancer profile. You can add your own work on top of it.</p>
          <div className="stack" role="radiogroup">
            {PERSONAS.map((x) => (
              <label key={x.id} className="choice">
                <input type="radio" name="persona" checked={persona === x.id} onChange={() => pick(x.id)} />
                <span><strong>{x.name}</strong> · {x.role}<br /><span className="small muted">Portfolio of case studies, repos, reviews and past proposals</span></span>
              </label>
            ))}
          </div>
          <label className="choice" style={{ marginTop: 12 }}>
            <input type="checkbox" checked={own} onChange={(e) => setOwn(e.target.checked)} />
            <span><strong>Make it my own profile</strong><br /><span className="small muted">Start a private, editable copy so you can upload your own work</span></span>
          </label>
        </section>}

        {step === 1 && <section>
          <h1>Connect a marketplace</h1>
          <p className="muted">GigBid reads jobs and sends approved proposals through this account.</p>
          <div className="field"><label htmlFor="acct">GigSim account (marketplace simulator)</label>
            <select id="acct" value={account} onChange={(e) => setAccount(e.target.value as PersonaId)}>
              {PERSONAS.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.role}</option>)}
            </select></div>
          <p className="small muted">Your account credential is stored encrypted and never shown or logged.</p>
          <hr />
          <div className="spread"><span><strong>Upwork</strong> <span className="small muted">(live mode via Upwork's official MCP server)</span></span>
            <button type="button" className="btn small" onClick={tryUpwork}>Connect Upwork</button></div>
          {upworkMsg && <p className="notice small" style={{ marginTop: 10 }}>{upworkMsg}</p>}
        </section>}

        {step === 2 && <section>
          <h1>Your portfolio</h1>
          <p className="muted">Proposals may only claim what your portfolio proves. {p.name}'s profile includes a CV, case
            studies, GitHub READMEs and code, client reviews, and past proposals labelled won, replied or ignored.</p>
          <p className="notice small">You can add your own case studies any time in Settings → Portfolio. Only new pieces are re-indexed.</p>
        </section>}

        {step === 3 && <section>
          <h1>Rates and budget</h1>
          <div className="grid2">
            <div className="field"><label htmlFor="floor">Minimum fixed price (USD)</label>
              <input id="floor" type="number" min={0} value={floor} onChange={(e) => setFloor(+e.target.value)} /></div>
            <div className="field"><label htmlFor="hourly">Minimum hourly rate (USD)</label>
              <input id="hourly" type="number" min={0} value={hourly} onChange={(e) => setHourly(+e.target.value)} /></div>
            <div className="field"><label htmlFor="budget">Weekly Connects budget</label>
              <input id="budget" type="number" min={0} max={500} value={budget} onChange={(e) => setBudget(+e.target.value)} /></div>
            <div className="field"><label htmlFor="kw">Saved search keywords (optional)</label>
              <input id="kw" placeholder={`e.g. ${p.cat === "ml" ? "RAG" : p.cat === "web" ? "Next.js" : "Power BI"}`} value={keywords} onChange={(e) => setKeywords(e.target.value)} /></div>
          </div>
          <div className="field"><label htmlFor="auto">Autonomy</label>
            <select id="auto" value={autonomy} onChange={(e) => setAutonomy(e.target.value as "manual" | "auto_skip")}>
              <option value="manual">Manual: I review every recommendation</option>
              <option value="auto_skip">Auto-skip low-fit jobs (never auto-send)</option>
            </select></div>
        </section>}

        {error && <ErrorBox error={error} />}
        <div className="spread" style={{ marginTop: 22 }}>
          <button className="btn ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
          {step < 3 ? <button className="btn primary" onClick={() => setStep(step + 1)}>Continue</button>
                    : <button className="btn primary" onClick={finish} disabled={busy}>{busy ? "Setting up…" : "Finish and find jobs"}</button>}
        </div>
      </div>
    </div>
  );
}
