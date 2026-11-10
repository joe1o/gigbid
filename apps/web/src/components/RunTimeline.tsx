// RunTimeline.tsx - live, node-by-node progress of an agent run (streamed over SSE).
import { useEventStream } from "../lib/hooks";

export type RunEvent = { ts: number; type: string; node?: string; label?: string; detail?: string; status?: string;
  tokens?: number; cost_usd?: number };

export function RunTimeline({ threadId, onFinish }: { threadId: string; onFinish?: (e: RunEvent) => void }) {
  const { events, open } = useEventStream<RunEvent>(`/api/runs/${encodeURIComponent(threadId)}/stream`);
  const last = events[events.length - 1];
  const running = last && last.type !== "done" && last.type !== "interrupt";
  if (last && !running && onFinish) setTimeout(() => onFinish(last), 0);
  return (
    <div>
      <div className="row small muted" style={{ marginBottom: 8 }}>
        <span className={`dot ${running ? "live" : ""}`} /> {running ? "Running…" : open ? "Connected" : "Waiting for events"}
      </div>
      {events.length === 0 ? <p className="muted small">No events yet for this run in this server session.</p> : (
        <ol className="timeline" aria-live="polite">
          {events.map((e, i) => (
            <li key={i}>
              <span className="dot" />
              <span>
                <strong>{e.label ?? e.node}</strong>
                {e.detail ? <div className="small muted">{e.detail}</div> : null}
              </span>
              <span className="small mono muted">
                {e.tokens ? `${e.tokens} tok ` : ""}{new Date(e.ts * 1000).toLocaleTimeString()}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
