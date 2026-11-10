// StudioPage.tsx - the proposal studio. The graph is PAUSED here waiting for you.
//   - every claim shows its evidence on hover (green = supported, amber = partly)
//   - Critic and Compliance notes inline
//   - regenerate one paragraph, edit, approve, or reject with a reason
//   - the dry-run preview shows exactly what will be sent and what it costs
// The pending approval lives in the checkpointer, so refreshing this page never loses it.
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EvidenceParagraph } from "../../components/EvidenceHover";
import { Empty, ErrorBox, FitBar, Loading, Money, RiskBadge } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

type Approval = {
  draft: { cover_letter: string; screening_answers: string[]; version: number; edited_by_user?: boolean };
  claims: { text: string; label: string; evidence_id?: string }[];
  evidence: { id: string; type: string; title: string; text: string }[];
  risk: { level: string; score: number }; fit: { score: number };
  price: { amount: number; rationale: string };
  critiques: { round: number; approved: boolean; issues: string[] }[];
  compliance?: { passed: boolean; fixes?: string[]; violations?: string[] } | null;
  preview: { connects_cost: number; balance_before: number; balance_after: number; policy_version: string; would_send: { bid_amount: number } };
  job: { title: string; job_id: string };
};

const split = (t: string) => t.split(/\n\s*\n/).filter((p) => p.trim());

export default function StudioPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const d = useLoad(async () => unwrap(await api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } })), [id]);
  const a = d.data?.approval as Approval | null | undefined;
  const [paras, setParas] = useState<string[]>([]);
  const [answers, setAnswers] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (a) { setParas(split(a.draft.cover_letter)); setAnswers(a.draft.screening_answers); setDirty(false); }
  }, [a]);

  if (d.error) return <ErrorBox error={d.error} retry={d.reload} />;
  if (!d.data) return <Loading lines={10} />;
  if (!a) return (
    <Empty title="Nothing waiting for approval">
      <p>Status: <strong>{d.data.summary.status.replace(/_/g, " ")}</strong></p>
      <Link className="btn" to={`/jobs/${id}`}>Open job</Link>
    </Empty>
  );

  async function decide(action: "approve" | "edit" | "reject") {
    setBusy(action);
    setError(null);
    try {
      const body = action === "edit" ? { action, cover_letter: paras.join("\n\n"), screening_answers: answers }
                 : action === "reject" ? { action, reason } : { action };
      const r = unwrap(await api.POST("/api/jobs/{job_id}/decision", { params: { path: { job_id: id } }, body }));
      nav(`/runs/${encodeURIComponent(r.thread_id)}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  async function regenerate(i: number) {
    setBusy(`regen-${i}`);
    try {
      const r = unwrap(await api.POST("/api/jobs/{job_id}/regenerate", { params: { path: { job_id: id } }, body: { paragraph_index: i, instruction: "" } }));
      setParas(paras.map((p, j) => (j === i ? r.paragraph : p)));
      setDirty(true);
      setEditing(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const lastCritique = a.critiques[a.critiques.length - 1];
  const words = paras.join(" ").split(/\s+/).filter(Boolean).length;

  return (
    <>
      <div className="page-head">
        <div><div className="eyebrow">Proposal studio · draft v{a.draft.version}{a.draft.edited_by_user ? " · edited by you" : ""}</div>
          <h1>{a.job.title}</h1>
          <div className="row"><FitBar score={a.fit.score} /><RiskBadge level={a.risk.level} /><Link to={`/jobs/${id}`} className="small">Job details</Link></div></div>
      </div>
      {error && <ErrorBox error={error} />}
      <div className="grid-main">
        <div>
          <div className="panel key letter">
            <div className="spread"><div className="eyebrow">Cover letter · <span className="num">{words}</span> words</div>
              <button className="btn small" onClick={() => setEditing(!editing)}>{editing ? "Preview with evidence" : "Edit"}</button></div>
            {paras.map((p, i) => (
              <div className="para" key={i}>
                {editing ? (
                  <textarea aria-label={`Paragraph ${i + 1}`} rows={4} value={p}
                    onChange={(e) => { setParas(paras.map((x, j) => (j === i ? e.target.value : x))); setDirty(true); }} />
                ) : <EvidenceParagraph text={p} claims={a.claims} evidence={a.evidence} />}
                <div className="para-tools">
                  <button className="btn small ghost" onClick={() => regenerate(i)} disabled={!!busy}>
                    {busy === `regen-${i}` ? "Rewriting…" : `Regenerate paragraph ${i + 1}`}</button>
                </div>
              </div>
            ))}
            {!editing && <p className="small muted">Hover or tab to an underlined sentence to see the evidence behind it.</p>}
          </div>
          {answers.length > 0 && <div className="panel"><div className="eyebrow">Screening answers</div>
            {answers.map((ans, i) => editing
              ? <div className="field" key={i}><label htmlFor={`ans-${i}`}>Answer {i + 1}</label>
                  <textarea id={`ans-${i}`} rows={3} value={ans} onChange={(e) => { setAnswers(answers.map((x, j) => (j === i ? e.target.value : x))); setDirty(true); }} /></div>
              : <EvidenceParagraph key={i} text={ans} claims={a.claims} evidence={a.evidence} />)}
          </div>}
          <div className="panel"><div className="eyebrow">Critic</div>
            {a.critiques.map((c) => <div key={c.round} className="small" style={{ marginBottom: 6 }}>
              Round {c.round + 1}: <span className={`badge ${c.approved ? "success" : "warning"}`}>{c.approved ? "approved" : "sent back"}</span>
              {c.issues.length > 0 && <ul className="issues">{c.issues.map((x, i) => <li key={i}>{x}</li>)}</ul>}</div>)}
            {!lastCritique?.approved && <p className="small muted">The Critic's revision limit (2) was reached; review its notes before approving.</p>}
          </div>
          {a.compliance && <div className="panel"><div className="eyebrow">Compliance Guard</div>
            {a.compliance.passed ? <p className="small"><span className="badge success">passed</span></p>
              : <div className="error small"><strong>Please fix before approving:</strong></div>}
            {[...(a.compliance.violations ?? []), ...(a.compliance.fixes ?? [])].map((x, i) => <p key={i} className="small">• {x}</p>)}
          </div>}
        </div>

        <aside>
          <div className="panel key" aria-label="What will be sent">
            <div className="eyebrow">Dry-run preview</div>
            <dl className="kv">
              <dt>Bid</dt><dd><Money v={a.preview.would_send.bid_amount} /></dd>
              <dt>Connects</dt><dd className="num">{a.preview.connects_cost}</dd>
              <dt>Balance</dt><dd className="num">{a.preview.balance_before} → {a.preview.balance_after}</dd>
              <dt>Policy</dt><dd className="mono small">{a.preview.policy_version}</dd>
            </dl>
            <p className="small muted" style={{ marginTop: 10 }}>{a.price.rationale}</p>
            <hr />
            {dirty ? <>
              <p className="small">You have unsaved changes. Saving re-checks them against the platform rules and your portfolio.</p>
              <button className="btn primary" style={{ width: "100%" }} onClick={() => decide("edit")} disabled={!!busy}>
                {busy === "edit" ? "Saving…" : "Save changes and re-check"}</button>
            </> : <button className="btn primary" style={{ width: "100%" }} onClick={() => decide("approve")} disabled={!!busy || a.compliance?.passed === false}>
                {busy === "approve" ? "Sending…" : `Approve and send (${a.preview.connects_cost} Connects)`}</button>}
            <hr />
            <label htmlFor="reason">Reject with a reason</label>
            <textarea id="reason" rows={2} placeholder="e.g. not my niche, budget too low" value={reason} onChange={(e) => setReason(e.target.value)} />
            <button className="btn danger" style={{ width: "100%", marginTop: 8 }} onClick={() => decide("reject")} disabled={!!busy || !reason.trim()}>
              {busy === "reject" ? "Rejecting…" : "Reject"}</button>
          </div>
        </aside>
      </div>
    </>
  );
}
