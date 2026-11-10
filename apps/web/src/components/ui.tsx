// ui.tsx - small building blocks used on every screen (badges, fit bar, empty/loading/error states).
import type { ReactNode } from "react";

const STATUS_TONE: Record<string, string> = {
  awaiting_approval: "accent", submitted: "success", analysing: "info", queued: "warning", watch: "warning",
  recommended_skip: "", skipped: "", rejected: "danger", blocked: "danger", needs_attention: "warning",
  dead_letter: "danger", error: "danger", replied: "success", interview: "success", hired: "success", lost: "",
};
const STATUS_LABEL: Record<string, string> = {
  awaiting_approval: "Needs your approval", recommended_skip: "Recommended skip", dead_letter: "Failed",
  needs_attention: "Needs attention", analysing: "Analysing", queued: "Queued (marketplace down)",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${STATUS_TONE[status] ?? ""}`}>{STATUS_LABEL[status] ?? status.replace(/_/g, " ")}</span>;
}

export function RiskBadge({ level }: { level?: string | null }) {
  if (!level) return <span className="badge">risk ?</span>;
  const tone = level === "high" ? "danger" : level === "medium" ? "warning" : "success";
  return <span className={`badge ${tone}`}>risk {level}</span>;
}

/** Hikmah-style segmented bar: 5 segments = fit score 0..1. */
export function FitBar({ score }: { score?: number | null }) {
  const on = score == null ? 0 : Math.round(score * 5);
  return (
    <span className="fitbar" aria-label={`fit ${score ?? "unknown"}`}>
      {[0, 1, 2, 3, 4].map((i) => <i key={i} className={i < on ? "on" : ""} />)}
      <span className="num">{score == null ? "–" : score.toFixed(2)}</span>
    </span>
  );
}

export function Money({ v }: { v?: number | null }) {
  return <span className="num">{v == null ? "–" : `$${Math.round(v).toLocaleString()}`}</span>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty panel"><h3>{title}</h3>{children}</div>;
}

export function Loading({ lines = 4 }: { lines?: number }) {
  return <div className="panel" aria-busy="true" aria-label="Loading">{Array.from({ length: lines }).map((_, i) =>
    <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />)}</div>;
}

export function ErrorBox({ error, retry }: { error: string; retry?: () => void }) {
  return <div className="error" role="alert">{error}{retry && <> <button className="btn small" onClick={retry}>Try again</button></>}</div>;
}
