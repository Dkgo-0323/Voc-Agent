"use client";

import { Sparkles } from "lucide-react";
import { useState } from "react";
import { EvidenceCard } from "@/components/evidence/evidence-card";
import { streamAsk } from "@/lib/api/ask";
import type { EvidenceCitation } from "@/lib/api/dashboard";

export function ControlledSummary({ skuA, skuB, weekId }: { skuA: string; skuB: string; weekId: number }) {
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<EvidenceCitation[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "error" | "done">("idle");
  const [error, setError] = useState("");

  const generate = async () => {
    setAnswer("");
    setCitations([]);
    setError("");
    setStatus("running");
    try {
      await streamAsk(`Compare ${skuA} and ${skuB} for ISO week ${weekId}. Give a neutral, grounded comparison. Use deterministic analytics for metrics and traceable evidence only where needed. Do not invent a winner or use product knowledge outside the configured VOC data.`, (event) => {
        if (event.event_type === "answer_delta") setAnswer((current) => current + event.delta);
        if (event.event_type === "citation") setCitations((current) => current.some((citation) => citation.mention_id === event.citation.mention_id) ? current : [...current, event.citation]);
        if (event.event_type === "error") { setError(event.error.message); setStatus("error"); }
      });
      setStatus((current) => current === "error" ? current : "done");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The comparison summary could not be generated.");
      setStatus("error");
    }
  };

  return <section className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--brand-soft)] p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand)]">Controlled Agent</p><h2 className="mt-2 text-xl font-semibold">Grounded comparison summary</h2><p className="mt-1 text-sm text-[var(--ink-muted)]">Uses the existing controlled Agent and its SQL/RAG/citation contracts for this visible pair and week.</p></div><button type="button" onClick={() => void generate()} disabled={status === "running"} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70"><Sparkles size={16} />{status === "running" ? "Generating…" : "Generate summary"}</button></div>{status === "running" ? <p className="mt-4 text-sm text-[var(--ink-muted)]">Calculating and retrieving grounded evidence…</p> : null}{error ? <p role="alert" className="mt-4 text-sm font-medium text-[var(--danger)]">{error}</p> : null}{answer ? <p className="mt-5 whitespace-pre-wrap text-sm leading-6">{answer}</p> : null}{citations.length ? <div className="mt-5 grid gap-4 lg:grid-cols-2">{citations.map((citation) => <EvidenceCard key={citation.mention_id} citation={citation} />)}</div> : null}</section>;
}
