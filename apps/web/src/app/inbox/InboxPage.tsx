// InboxPage.tsx - new jobs ranked by fit, with risk badges, recommended action, price and Connects cost.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, FitBar, Loading, Money, RiskBadge, StatusBadge } from "../../components/ui";
import { api, unwrap, type JobSummary } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

const TABS = [
  ["all", "All"], ["awaiting_approval", "Needs approval"], ["analysing", "Analysing"],
  ["recommended_skip", "Recommended skip"], ["submitted", "Submitted"],
] as const;

export default function InboxPage() {
  const [tab, setTab] = useState<string>("all");
  const [scouting, setScouting] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const jobs = useLoad(async () => unwrap(await api.GET("/api/jobs")), [], 3000,
    (d) => d.some((j) => j.status === "analysing" || j.status === "queued"));

  async function scout() {
    setScouting(true);
    try {
      const r = unwrap(await api.POST("/api/scout"));
      setNote(r.new_jobs ? `Found ${r.new_jobs} new job(s)${r.duplicates ? `, ignored ${r.duplicates} repost(s)` : ""}. Analysing now…`
                         : "No new jobs since the last check.");
      jobs.reload();
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setScouting(false);
    }
  }

  async function skip(j: JobSummary) {
    unwrap(await api.POST("/api/jobs/{job_id}/skip", { params: { path: { job_id: j.job_id } } }));
    jobs.reload();
  }

  const rows = (jobs.data ?? []).filter((j) => tab === "all" || j.status === tab);
  const count = (s: string) => (jobs.data ?? []).filter((j) => j.status === s).length;

  return (
    <>
      <div className="page-head">
        <div><div className="eyebrow">Inbox</div><h1>Jobs worth a look</h1>
          <p className="muted">Ranked by fit. Scams and poor fits are flagged before you spend a single Connect.</p></div>
        <button className="btn primary" onClick={scout} disabled={scouting}>{scouting ? "Searching…" : "Find new jobs"}</button>
      </div>
      {note && <p className="notice small" role="status">{note}</p>}
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {label}{k !== "all" && count(k) ? ` (${count(k)})` : ""}
          </button>
        ))}
      </div>
      {jobs.error && <ErrorBox error={jobs.error} retry={jobs.reload} />}
      {jobs.loading && !jobs.data ? <Loading /> : rows.length === 0 ? (
        <Empty title={jobs.data?.length ? "Nothing in this tab" : "No jobs yet"}>
          <p>{jobs.data?.length ? "Try another tab." : "Run your saved searches to pull in new jobs."}</p>
          {!jobs.data?.length && <button className="btn primary" onClick={scout}>Find new jobs</button>}
        </Empty>
      ) : (
        <>
          <table className="table responsive panel" style={{ padding: 0 }}>
            <thead><tr><th>Job</th><th>Fit</th><th>Risk</th><th>Recommendation</th><th>Price</th><th>Connects</th><th /></tr></thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.job_id}>
                  <td><Link className="job-title" to={j.status === "awaiting_approval" ? `/studio/${j.job_id}` : `/jobs/${j.job_id}`}>{j.title}</Link>
                    <div className="small muted"><span className="mono">{j.job_id}</span> · {j.category} · <Money v={j.budget_min} />–<Money v={j.budget_max} /></div></td>
                  <td><FitBar score={j.fit} /></td>
                  <td><RiskBadge level={j.risk_level} /></td>
                  <td><StatusBadge status={j.status} /></td>
                  <td><Money v={j.price} /></td>
                  <td className="num">{j.connects_cost}</td>
                  <td><div className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
                    <Link className="btn small" to={j.status === "awaiting_approval" ? `/studio/${j.job_id}` : `/jobs/${j.job_id}`}>Open</Link>
                    {!["submitted", "skipped", "analysing"].includes(j.status) &&
                      <button className="btn small ghost" onClick={() => skip(j)} aria-label={`Skip ${j.title}`}>Skip</button>}
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="cards">
            {rows.map((j) => (
              <Link key={j.job_id} className="card-row" to={j.status === "awaiting_approval" ? `/studio/${j.job_id}` : `/jobs/${j.job_id}`}>
                <div className="job-title">{j.title}</div>
                <div className="row small" style={{ marginTop: 6 }}><FitBar score={j.fit} /><RiskBadge level={j.risk_level} /><StatusBadge status={j.status} /></div>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}
