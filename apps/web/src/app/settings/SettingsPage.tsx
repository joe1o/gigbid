// SettingsPage.tsx - autonomy, budgets, saved searches, connected accounts, portfolio, and the
// memory viewer where you can see and delete what GigBid has learned about you.
import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "../../components/ui";
import { api, unwrap, type Settings } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

type ItemType = "case_study" | "repo_readme" | "code" | "review" | "past_proposal" | "cv";

export default function SettingsPage() {
  const me = useLoad(async () => unwrap(await api.GET("/api/me")), []);
  const mem = useLoad(async () => unwrap(await api.GET("/api/memory")), []);
  const pf = useLoad(async () => unwrap(await api.GET("/api/portfolio")), []);
  const [s, setS] = useState<Settings | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [item, setItem] = useState({ type: "case_study" as ItemType, title: "", skills: "", text: "" });
  useEffect(() => { if (me.data?.settings) setS(me.data.settings); }, [me.data]);
  if (!s || !me.data) return me.error ? <ErrorBox error={me.error} /> : <Loading lines={8} />;

  async function save() {
    try {
      unwrap(await api.PUT("/api/settings", { body: { fixed_floor_usd: s!.fixed_floor_usd, hourly_floor_usd: s!.hourly_floor_usd,
        connects_weekly_budget: s!.connects_weekly_budget, autonomy: s!.autonomy ?? "manual", searches: s!.searches ?? [] } }));
      setSaved("Settings saved.");
    } catch (e) { setError((e as Error).message); }
  }
  async function forget(ns: string, key: string) {
    unwrap(await api.DELETE("/api/memory/{namespace}/{key}", { params: { path: { namespace: ns, key } } }));
    mem.reload();
  }
  async function addItem(e: React.FormEvent) {
    e.preventDefault();
    try {
      unwrap(await api.POST("/api/portfolio/items", { body: { type: item.type, title: item.title, text: item.text,
        skills: item.skills.split(",").map((x) => x.trim()).filter(Boolean) } }));
      setItem({ type: "case_study", title: "", skills: "", text: "" });
      pf.reload();
      setSaved("Added to your portfolio. Only the new piece was indexed.");
    } catch (err) { setError((err as Error).message); }
  }
  const search = s.searches?.[0] ?? { query: "", category: null };

  return (
    <>
      <div className="page-head"><div><div className="eyebrow">Settings</div><h1>How GigBid works for you</h1></div></div>
      {saved && <p className="notice small" role="status">{saved}</p>}
      {error && <ErrorBox error={error} />}
      <div className="grid2">
        <div className="panel key"><div className="eyebrow">Autonomy and budgets</div>
          <div className="field"><label htmlFor="autonomy">Autonomy</label>
            <select id="autonomy" value={s.autonomy ?? "manual"} onChange={(e) => setS({ ...s, autonomy: e.target.value as "manual" | "auto_skip" })}>
              <option value="manual">Manual: I review every recommendation</option>
              <option value="auto_skip">Auto-skip low-fit jobs (never auto-send)</option></select></div>
          <div className="grid2">
            <div className="field"><label htmlFor="floor">Minimum fixed price</label><input id="floor" type="number" value={s.fixed_floor_usd} onChange={(e) => setS({ ...s, fixed_floor_usd: +e.target.value })} /></div>
            <div className="field"><label htmlFor="hourly">Minimum hourly</label><input id="hourly" type="number" value={s.hourly_floor_usd} onChange={(e) => setS({ ...s, hourly_floor_usd: +e.target.value })} /></div>
            <div className="field"><label htmlFor="budget">Weekly Connects budget</label><input id="budget" type="number" value={s.connects_weekly_budget} onChange={(e) => setS({ ...s, connects_weekly_budget: +e.target.value })} /></div>
            <div className="field"><label htmlFor="kw">Saved search keywords</label><input id="kw" value={search.query ?? ""} onChange={(e) => setS({ ...s, searches: [{ ...search, query: e.target.value }] })} /></div>
          </div>
          <button className="btn primary" onClick={save}>Save settings</button>
        </div>
        <div className="panel"><div className="eyebrow">Connected accounts</div>
          <dl className="kv"><dt>GigSim</dt><dd>{me.data.gigsim ? <><span className="badge success">connected</span> <span className="mono small">{me.data.gigsim.account}</span></> : "not connected"}</dd>
            <dt>Upwork</dt><dd><span className="badge">not configured</span> <span className="small muted">live mode needs an Upwork OAuth app</span></dd></dl>
          <p className="small muted" style={{ marginTop: 10 }}>Credentials are stored encrypted and never logged.</p>
        </div>
      </div>

      <div className="panel"><div className="eyebrow">What GigBid has learned about you</div>
        <p className="small muted">Learned only through promotion rules: a style rule needs the same edit in 2 separate drafts; an outcome summary needs 3 results in a category.</p>
        {!mem.data ? <Loading lines={2} /> : mem.data.length === 0 ? <p className="small">Nothing yet. Edit a few drafts and GigBid will pick up your style.</p> :
          <table className="table"><tbody>{mem.data.map((m) => (
            <tr key={m.namespace + m.key}><td><span className="badge">{m.namespace.replace("~", " / ")}</span></td>
              <td>{m.rule ?? `reply rate ${Math.round(((m.value.reply_rate as number) ?? 0) * 100)}% over ${m.value.results} results`}
                <div className="small muted">{m.value.promotion_rule as string}</div></td>
              <td><button className="btn small danger" onClick={() => forget(m.namespace, m.key)} aria-label={`Delete memory ${m.key}`}>Delete</button></td></tr>))}</tbody></table>}
      </div>

      <div className="panel"><div className="spread"><div className="eyebrow">Portfolio · {pf.data?.name} · {pf.data?.items.length ?? 0} items</div>
        {pf.data && !pf.data.editable && <span className="small muted">Adding an item creates your private copy</span>}</div>
        <form onSubmit={addItem} className="grid2" aria-label="Add portfolio item">
          <div className="field"><label htmlFor="it-type">Type</label><select id="it-type" value={item.type} onChange={(e) => setItem({ ...item, type: e.target.value as ItemType })}>
            <option value="case_study">Case study</option><option value="repo_readme">Repo README</option><option value="code">Code</option>
            <option value="review">Client review</option><option value="past_proposal">Past proposal</option><option value="cv">CV</option></select></div>
          <div className="field"><label htmlFor="it-title">Title</label><input id="it-title" required minLength={3} value={item.title} onChange={(e) => setItem({ ...item, title: e.target.value })} /></div>
          <div className="field" style={{ gridColumn: "1 / -1" }}><label htmlFor="it-text">What you did and what it achieved (with real numbers)</label>
            <textarea id="it-text" rows={3} required minLength={20} value={item.text} onChange={(e) => setItem({ ...item, text: e.target.value })} /></div>
          <div className="field"><label htmlFor="it-skills">Skills (comma separated)</label><input id="it-skills" value={item.skills} onChange={(e) => setItem({ ...item, skills: e.target.value })} /></div>
          <div className="field" style={{ alignSelf: "end" }}><button className="btn">Add to portfolio</button></div>
        </form>
        <details><summary className="small">Show all items</summary>
          {(pf.data?.items ?? []).map((it) => <p key={it.id as string} className="small"><span className="mono">{it.id as string}</span> · {it.title as string}</p>)}</details>
      </div>
    </>
  );
}
