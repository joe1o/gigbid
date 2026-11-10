// JobPage.tsx - everything the agents found about one job: JobSpec, risk report,
// requirement-to-evidence matrix, price rationale and the bid/skip reasoning.
import { Link, useNavigate, useParams } from "react-router-dom";
import { Empty, ErrorBox, FitBar, Loading, Money, RiskBadge, StatusBadge } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

type Row = { requirement: string; evidence_ids: string[]; status: string; top_score?: number | null };

export default function JobPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const d = useLoad(async () => unwrap(await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })), [id], 3000,
    (x) => x.summary.status === "analysing");
  if (d.error) return <ErrorBox error={d.error} retry={d.reload} />;
  if (!d.data) return <Loading lines={8} />;
  const { summary: s, state, job } = d.data;
  const spec = state.job_spec as Record<string, string[] | string> | undefined;
  const risk = state.risk as { score: number; level: string; flags: string[]; explanation: string; client: Record<string, unknown> } | undefined;
  const fit = state.fit as { score: number; matrix: Row[]; reasons: string[] } | undefined;
  const price = state.price as { amount: number; rationale: string; connects_cost: number; connects_balance: number } | undefined;
  const decision = state.decision as { action: string; reasons: string[] } | undefined;

  async function act(path: "/api/jobs/{job_id}/draft" | "/api/jobs/{job_id}/retry") {
    const r = unwrap(await api.POST(path, { params: { path: { job_id: id } } }));
    nav(`/runs/${encodeURIComponent(r.thread_id)}`);
  }

  return (
    <>
      <div className="page-head">
        <div><div className="eyebrow">Job · {s.job_id} · {s.category}</div><h1>{s.title}</h1>
          <div className="row"><StatusBadge status={s.status} /><RiskBadge level={s.risk_level} /><FitBar score={s.fit} />
            <span className="small muted">Budget <Money v={s.budget_min} />–<Money v={s.budget_max} /> · {s.connects_cost} Connects</span></div></div>
        <div className="row">
          {s.status === "awaiting_approval" && <Link className="btn primary" to={`/studio/${id}`}>Open proposal studio</Link>}
          {["recommended_skip", "watch"].includes(s.status) && s.risk_level !== "high" &&
            <button className="btn" onClick={() => act("/api/jobs/{job_id}/draft")}>Draft anyway</button>}
          {["queued", "error", "dead_letter", "needs_attention"].includes(s.status) &&
            <button className="btn" onClick={() => act("/api/jobs/{job_id}/retry")}>Retry</button>}
          <Link className="btn ghost" to={`/runs/${encodeURIComponent(s.thread_id)}`}>View run</Link>
        </div>
      </div>
      {s.error && <p className="error small">{s.error}</p>}
      {s.status === "analysing" && !decision ? <Loading lines={6} /> : <>
        {decision && <div className="panel key"><div className="eyebrow">Recommendation</div>
          <h2 style={{ textTransform: "capitalize" }}>{decision.action}</h2>
          <ul className="issues">{decision.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}

        <div className="grid2" style={{ marginTop: 14 }}>
          <div className="panel"><div className="eyebrow">Job spec (Job Analyst)</div>
            {spec ? <>
              <p>{spec.summary as string}</p>
              <dl className="kv">
                <dt>Requirements</dt><dd>{(spec.requirements as string[]).join(", ")}</dd>
                <dt>Deliverables</dt><dd>{(spec.deliverables as string[]).join("; ") || "–"}</dd>
                <dt>Hidden needs</dt><dd>{(spec.hidden_needs as string[]).join("; ") || "–"}</dd>
              </dl>
              {(spec.suspicious_instructions as string[]).length > 0 && <div className="error small" style={{ marginTop: 10 }}>
                <strong>Ignored instructions found in the post:</strong>
                <ul className="issues">{(spec.suspicious_instructions as string[]).map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
            </> : <p className="muted">Not analysed.</p>}
          </div>
          <div className="panel"><div className="eyebrow">Risk report (Risk Assessor)</div>
            {risk ? <>
              <div className="row"><RiskBadge level={risk.level} /><span className="num">{risk.score}</span></div>
              <p className="small" style={{ marginTop: 8 }}>{risk.explanation || "No risk signals."}</p>
              <dl className="kv small">
                <dt>Client spent</dt><dd><Money v={risk.client.total_spent_usd as number} /></dd>
                <dt>Hires</dt><dd>{String(risk.client.hires)}</dd>
                <dt>Payment verified</dt><dd>{risk.client.payment_verified ? "yes" : "no"}</dd>
                <dt>Account age</dt><dd>{String(risk.client.account_age_days)} days</dd>
              </dl>
            </> : <p className="muted">Not analysed.</p>}
          </div>
        </div>

        <div className="panel"><div className="eyebrow">Requirement → evidence (Fit Matcher)</div>
          {fit ? <>
            <p className="small muted">{fit.reasons.join(" · ")}</p>
            <table className="table matrix"><thead><tr><th>Requirement</th><th>Proof in your portfolio</th><th>Status</th></tr></thead>
              <tbody>{fit.matrix.map((r) => <tr key={r.requirement}><td>{r.requirement}</td>
                <td className="mono small">{r.evidence_ids.slice(0, 3).join(", ") || "–"}</td>
                <td><span className={`badge ${r.status === "found" ? "success" : "danger"}`}>{r.status === "found" ? "evidence" : "no evidence"}</span></td></tr>)}</tbody></table>
          </> : <p className="muted">Not analysed.</p>}
        </div>

        {price && <div className="panel"><div className="eyebrow">Price (Pricing Strategist)</div>
          <div className="stat"><Money v={price.amount} /></div><p className="small">{price.rationale}</p></div>}

        <details className="panel"><summary>Original job post <span className="small muted">(untrusted text, shown as written)</span></summary>
          <p style={{ whiteSpace: "pre-wrap", marginTop: 10 }}>{(job as { description?: string }).description}</p></details>
      </>}
      {!decision && s.status !== "analysing" && <Empty title="No analysis yet" />}
    </>
  );
}
