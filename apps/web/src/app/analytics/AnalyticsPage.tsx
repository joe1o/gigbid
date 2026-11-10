// AnalyticsPage.tsx - reply/hire rate by category, Connects spent vs outcomes, cost and latency,
// top rejection and skip reasons.
import { Empty, ErrorBox, Loading } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

function Bars({ rows, fmt = (v: number) => String(v) }: { rows: { label: string; count: number }[]; fmt?: (v: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <p className="small muted">No data yet.</p>;
  return <>{rows.map((r) => (
    <div className="bar-row" key={r.label}><span className="small">{r.label}</span>
      <span className="bar"><i style={{ width: `${(100 * r.count) / max}%` }} /></span><span className="num small">{fmt(r.count)}</span></div>))}</>;
}

export default function AnalyticsPage() {
  const d = useLoad(async () => unwrap(await api.GET("/api/analytics")), []);
  if (d.error) return <ErrorBox error={d.error} retry={d.reload} />;
  if (!d.data) return <Loading lines={8} />;
  const a = d.data;
  return (
    <>
      <div className="page-head"><div><div className="eyebrow">Analytics</div><h1>What is working</h1></div></div>
      <div className="grid2">
        <div className="panel"><div className="eyebrow">Jobs analysed</div><div className="stat">{a.proposals_analysed}</div></div>
        <div className="panel"><div className="eyebrow">Agent time per job (p50 / p95)</div>
          <div className="stat">{a.p50_seconds_per_job}s / {a.p95_seconds_per_job}s</div></div>
        <div className="panel"><div className="eyebrow">Model cost per job analysed</div><div className="stat">${a.avg_cost_usd_per_job.toFixed(4)}</div></div>
        <div className="panel"><div className="eyebrow">Model cost per proposal</div><div className="stat">${a.avg_cost_usd_per_proposal.toFixed(4)}</div></div>
      </div>
      <div className="panel"><div className="eyebrow">Reply and hire rate by category</div>
        {a.by_category.length === 0 ? <Empty title="No proposals sent yet" /> : (
          <table className="table"><thead><tr><th>Category</th><th>Sent</th><th>Replied</th><th>Hired</th><th>Reply rate</th><th>Hire rate</th></tr></thead>
            <tbody>{a.by_category.map((c) => <tr key={c.category}><td>{c.category}</td><td className="num">{c.sent}</td><td className="num">{c.replied}</td>
              <td className="num">{c.hired}</td><td className="num">{Math.round(c.reply_rate * 100)}%</td><td className="num">{Math.round(c.hire_rate * 100)}%</td></tr>)}</tbody></table>)}
      </div>
      <div className="grid2" style={{ marginTop: 14 }}>
        <div className="panel"><div className="eyebrow">Connects spent by outcome</div><Bars rows={a.connects_by_outcome} /></div>
        <div className="panel"><div className="eyebrow">Why you rejected drafts</div><Bars rows={a.rejection_reasons} /></div>
      </div>
      <div className="panel"><div className="eyebrow">Why jobs were skipped</div><Bars rows={a.skip_reasons} /></div>
    </>
  );
}
