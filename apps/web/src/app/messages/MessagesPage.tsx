// MessagesPage.tsx - client conversations. GigBid drafts a reply (and interview slots);
// you approve, edit or reject it before anything is sent.
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Empty, ErrorBox, Loading, StatusBadge } from "../../components/ui";
import { api, unwrap } from "../../lib/api/client";
import { useLoad } from "../../lib/hooks";

type Pending = { reply: string; intent: { intent: string; summary: string; injections?: string[] };
  slots: { label: string }[]; compliance?: { passed: boolean; fixes?: string[]; violations?: string[] } };

export default function MessagesPage() {
  const { threadId } = useParams();
  const nav = useNavigate();
  const list = useLoad(async () => unwrap(await api.GET("/api/threads")), [], 10000, () => true);
  const t = useLoad(async () => threadId ? unwrap(await api.GET("/api/threads/{thread_id}", { params: { path: { thread_id: threadId } } })) : null,
    [threadId], 4000, (x) => !!x && !x.approval);
  const pending = t.data?.approval as Pending | undefined;
  const [reply, setReply] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (pending) setReply(pending.reply); }, [pending]);

  async function draft() {
    setBusy("draft");
    try {
      const r = unwrap(await api.POST("/api/threads/{thread_id}/draft", { params: { path: { thread_id: threadId! } } }));
      nav(`/runs/${encodeURIComponent(r.thread_id)}`);
    } catch (e) { setError((e as Error).message); setBusy(null); }
  }
  async function decide(action: "approve" | "edit" | "reject") {
    setBusy(action);
    try {
      const body = action === "edit" ? { action, cover_letter: reply } : action === "reject" ? { action, reason } : { action };
      const r = unwrap(await api.POST("/api/threads/{thread_id}/decision", { params: { path: { thread_id: threadId! } }, body }));
      nav(`/runs/${encodeURIComponent(r.thread_id)}`);
    } catch (e) { setError((e as Error).message); setBusy(null); }
  }

  return (
    <>
      <div className="page-head"><div><div className="eyebrow">Messages</div><h1>Client conversations</h1></div></div>
      {list.error && <ErrorBox error={list.error} retry={list.reload} />}
      <div className="split">
        <nav aria-label="Conversations">
          {!list.data ? <Loading /> : list.data.length === 0 ? <Empty title="No replies yet"><p className="small">Client replies to your proposals appear here.</p></Empty> :
            list.data.map((x) => (
              <Link key={x.thread_id} to={`/messages/${x.thread_id}`} className={`list-item ${x.thread_id === threadId ? "active" : ""}`}>
                <div className="spread"><strong className="small">{x.job_title || x.job_id}</strong>{x.unanswered && <span className="badge accent">new</span>}</div>
                <div className="small muted">{x.last_message.text.slice(0, 80)}</div>
                <div className="row" style={{ marginTop: 4 }}><StatusBadge status={x.status} />{x.draft_status && <StatusBadge status={x.draft_status} />}</div>
              </Link>))}
        </nav>
        <section>
          {!threadId ? <Empty title="Pick a conversation" /> : !t.data ? <Loading /> : <>
            <div className="panel"><div className="eyebrow">{t.data.job_title}</div>
              <div className="chat">{t.data.messages.map((m) => (
                <div key={m.id as number} className={`bubble ${m.sender === "freelancer" ? "me" : ""}`}>
                  <div className="eyebrow" style={{ marginBottom: 4 }}>{m.sender === "freelancer" ? "you" : "client"}</div>{m.text as string}</div>))}
              </div></div>
            {error && <ErrorBox error={error} />}
            {pending ? (
              <div className="panel key">
                <div className="eyebrow">Suggested reply · intent: {pending.intent.intent.replace(/_/g, " ")}</div>
                <p className="small muted">{pending.intent.summary}</p>
                {pending.intent.injections?.length ? <p className="error small">Ignored instructions inside the client's message: {pending.intent.injections.join(" ")}</p> : null}
                {pending.slots.length > 0 && <p className="small">Offered times (tentative holds on approval): {pending.slots.map((s) => s.label).join(" · ")}</p>}
                <label htmlFor="reply">Reply</label>
                <textarea id="reply" rows={5} value={reply} onChange={(e) => setReply(e.target.value)} />
                {pending.compliance && !pending.compliance.passed && <p className="error small">{(pending.compliance.violations ?? []).join("; ")}</p>}
                <div className="row" style={{ marginTop: 10 }}>
                  {reply !== pending.reply ? <button className="btn primary" onClick={() => decide("edit")} disabled={!!busy}>Save changes and re-check</button>
                    : <button className="btn primary" onClick={() => decide("approve")} disabled={!!busy}>Approve and send</button>}
                  <input aria-label="Reason for rejecting" placeholder="Reason to reject" style={{ maxWidth: 220 }} value={reason} onChange={(e) => setReason(e.target.value)} />
                  <button className="btn danger" onClick={() => decide("reject")} disabled={!!busy || !reason.trim()}>Reject</button>
                </div>
              </div>
            ) : t.data.messages.length > 0 && t.data.messages[t.data.messages.length - 1].sender === "client" ? (
              <button className="btn primary" onClick={draft} disabled={!!busy}>{busy ? "Starting…" : "Draft a reply with GigBid"}</button>
            ) : <p className="small muted">Waiting for the client.</p>}
          </>}
        </section>
      </div>
    </>
  );
}
