// RunPage.tsx - the agent run viewer: live node-by-node progress (SSE), the saved checkpoints,
// and a link to the full trace.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RunTimeline, type RunEvent } from "../../components/RunTimeline";
import { api, unwrap } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

export default function RunPage() {
  const { threadId = "" } = useParams();
  const [kind, , jobId] = threadId.split(":");
  const [final, setFinal] = useState<RunEvent | null>(null);
  const info = useLoad(async () => unwrap(await api.GET("/api/runs/{thread_id}/events", { params: { path: { thread_id: threadId } } })) as
    { trace_url?: string | null; trace_filter: string }, [threadId]);
  const hist = useLoad(async () => kind === "bid"
    ? unwrap(await api.GET("/api/jobs/{job_id}/history", { params: { path: { job_id: jobId } } })) : [], [threadId, final?.ts]);

  const next = final?.type === "interrupt" ? (kind === "bid" ? `/studio/${jobId}` : `/messages/${jobId}`)
             : kind === "bid" ? `/jobs/${jobId}` : `/messages/${jobId}`;
  return (
    <>
      <div className="page-head">
        <div><div className="eyebrow">Agent run</div><h1 className="mono" style={{ fontSize: 20 }}>{threadId}</h1>
          <p className="muted">Each line is one agent finishing its step, streamed live from LangGraph.</p></div>
        <div className="row">
          {final && <Link className="btn primary" to={next}>{final.type === "interrupt" ? "Review and approve" : "Open result"}</Link>}
          {info.data?.trace_url && <a className="btn" href={info.data.trace_url} target="_blank" rel="noreferrer">Full trace</a>}
        </div>
      </div>
      <div className="grid-main">
        <div className="panel key"><RunTimeline threadId={threadId} onFinish={(e) => setFinal((f) => f ?? e)} /></div>
        <aside className="panel">
          <div className="eyebrow">Saved checkpoints</div>
          <p className="small muted">The graph's state is saved after every step (Postgres), so a crash or restart resumes here.</p>
          {(hist.data ?? []).slice(0, 14).map((h) => (
            <div key={h.checkpoint_id} className="small spread" style={{ borderBottom: "1px solid rgb(var(--border))", padding: "5px 0" }}>
              <span>step {h.step ?? "–"} → {h.next.join(", ") || "end"}</span><span className="muted">{h.status ?? ""}</span></div>
          ))}
          {info.data && !info.data.trace_url && <p className="small muted" style={{ marginTop: 10 }}>Tracing: filter <code>{info.data.trace_filter}</code> in LangSmith.</p>}
        </aside>
      </div>
    </>
  );
}
