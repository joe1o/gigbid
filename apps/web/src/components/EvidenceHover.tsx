// EvidenceHover.tsx - shows a proposal paragraph where every CLAIM is underlined; hovering
// (or tabbing to) a claim shows the portfolio evidence behind it.
//   green dotted = supported, amber = partly supported (unsupported ones were already removed).
type Claim = { text: string; label: string; evidence_id?: string | null };
type Evidence = { id: string; type: string; title: string; text: string };

export function EvidenceParagraph({ text, claims, evidence }: { text: string; claims: Claim[]; evidence: Evidence[] }) {
  const byId = new Map(evidence.map((e) => [e.id, e]));
  // Split the paragraph into sentences and match each to a checked claim.
  const sentences = text.split(/(?<=[.!?])\s+/);
  return (
    <p>
      {sentences.map((s, i) => {
        const c = claims.find((c) => c.text.trim() === s.trim());
        const ev = c?.evidence_id ? byId.get(c.evidence_id) : undefined;
        if (!c || !ev) return <span key={i}>{s} </span>;
        return (
          <span key={i}>
            <span className={`claim ${c.label}`} tabIndex={0} aria-label={`${c.label.replace("_", " ")} by ${ev.title}`}>
              {s}
              <span className="tip" role="tooltip">
                <span className="eyebrow">{c.label.replace("_", " ")} · {ev.type.replace("_", " ")} · {ev.id}</span>
                <strong>{ev.title}</strong>
                <br />
                {ev.text.length > 260 ? ev.text.slice(0, 260) + "…" : ev.text}
              </span>
            </span>{" "}
          </span>
        );
      })}
    </p>
  );
}
