import type { EvidenceCitation } from "@/lib/api/dashboard";

function titleFromAspect(aspect: string) {
  return aspect
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatSourceDate(value: string | null) {
  if (!value) {
    return null;
  }
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function EvidenceCard({ citation }: { citation: EvidenceCitation }) {
  const publishedAt = formatSourceDate(citation.source.published_at);

  return <article className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 shadow-[var(--shadow)]"><div className="flex flex-wrap items-center gap-2 text-xs font-semibold"><span className={citation.sentiment === "positive" ? "rounded-full bg-[var(--brand-soft)] px-2.5 py-1 text-[var(--brand-strong)]" : "rounded-full bg-[#fae9e7] px-2.5 py-1 text-[var(--danger)]"}>{citation.sentiment}</span><span className="text-[var(--ink-muted)]">{titleFromAspect(citation.aspect_label)}</span><span className="text-[var(--ink-muted)]">Week {citation.week_id}</span></div><blockquote className="mt-3 text-sm leading-6 text-[var(--ink)]">“{citation.evidence_preview}”</blockquote><p className="mt-3 text-xs text-[var(--ink-muted)]">{citation.source.platform}{publishedAt ? ` · ${publishedAt}` : ""}{citation.source.rating ? ` · ${citation.source.rating}/5` : ""}</p><details className="mt-3 border-t border-[var(--line)] pt-3"><summary className="cursor-pointer text-sm font-semibold text-[var(--brand-strong)]">Source and provenance</summary><div className="mt-3 space-y-2 text-xs leading-5 text-[var(--ink-muted)]"><p>Evidence ID: <span className="font-mono text-[11px]">{citation.mention_id}</span></p><p>Document ID: <span className="font-mono text-[11px]">{citation.document_id}</span></p>{citation.source.title ? <p>{citation.source.title}</p> : null}{citation.source.review_text ? <p className="rounded-lg bg-[var(--surface-muted)] p-3 text-sm leading-6 text-[var(--ink)]">{citation.source.review_text}</p> : null}{citation.source.source_url ? <a href={citation.source.source_url} target="_blank" rel="noreferrer" className="font-semibold text-[var(--brand-strong)]">Open original source</a> : null}</div></details></article>;
}
