// PipelinePage.tsx - kanban board: drafted -> submitted -> viewed -> replied -> interview -> hired / lost.
// Cards update from the marketplace (polled every 10 s).
import { Link } from "react-router-dom";
import { ErrorBox, Loading, Money } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"];

export default function PipelinePage() {
  const d = useLoad(async () => unwrap(await api.GET("/api/pipeline")), [], 10000, () => true);
  return (
    <>
      <div className="page-head"><div><div className="eyebrow">Pipeline</div><h1>Where every proposal stands</h1>
        <p className="muted">Updates automatically from the marketplace.</p></div></div>
      {d.error && <ErrorBox error={d.error} retry={d.reload} />}
      {!d.data ? <Loading /> : (
        <div className="board">
          {COLS.map((c) => {
            const cards = d.data!.columns[c] ?? [];
            return (
              <section className="col" key={c} aria-label={c}>
                <h3><span>{c}</span><span>{cards.length}</span></h3>
                {cards.length === 0 && <p className="small muted">–</p>}
                {cards.map((k) => (
                  <Link key={k.job_id + (k.proposal_id ?? "")} className="kcard"
                    to={c === "drafted" ? `/studio/${k.job_id}` : ["replied", "interview", "hired"].includes(c) && k.proposal_id ? `/messages/${k.proposal_id}` : `/jobs/${k.job_id}`}>
                    <strong>{k.title}</strong>
                    <div className="small muted">{k.category} · <Money v={k.bid_amount} />{k.connects_spent ? ` · ${k.connects_spent} Connects` : ""}</div>
                  </Link>
                ))}
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
