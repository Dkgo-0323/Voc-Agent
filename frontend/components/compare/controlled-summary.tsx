"use client";

import { CircleStop, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { EvidenceCard } from "@/components/evidence/evidence-card";
import { toApiError } from "@/lib/api/client";
import type { EvidenceCitation } from "@/lib/api/dashboard";
import { streamAsk } from "@/lib/api/ask";

export function ControlledSummary({ skuA, skuB, weekId }: { skuA: string; skuB: string; weekId: number }) {
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<EvidenceCitation[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "error" | "done" | "cancelled">("idle");
  const [error, setError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  const generate = async () => {
    if (status === "running") return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setAnswer("");
    setCitations([]);
    setError("");
    setStatus("running");
    let terminalEventReceived = false;
    let streamError = "";
    try {
      await streamAsk(`Compare ${skuA} and ${skuB} for ISO week ${weekId}. Give a neutral, grounded comparison. Use deterministic analytics for metrics and traceable evidence only where needed. Do not invent a winner or use product knowledge outside the configured VOC data.`, (event) => {
        if (event.event_type === "answer_delta") setAnswer((current) => current + event.delta);
        if (event.event_type === "citation") setCitations((current) => current.some((citation) => citation.mention_id === event.citation.mention_id) ? current : [...current, event.citation]);
        if (event.event_type === "done") { terminalEventReceived = true; if (event.status === "error") streamError = "The comparison response could not be completed. Please try again."; }
        if (event.event_type === "error") { terminalEventReceived = true; streamError = event.error.message; }
      }, { signal: controller.signal });
      if (streamError || !terminalEventReceived) {
        setError(streamError || "The comparison response ended before it was completed. Please try again.");
        setStatus("error");
      } else setStatus("done");
    } catch (caught) {
      if (controller.signal.aborted) setStatus("cancelled");
      else { setError(toApiError(caught).message); setStatus("error"); }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  };

  return <section className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--brand-soft)] p-5"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand)]">Controlled Agent</p><h2 className="mt-2 text-xl font-semibold">Grounded comparison summary</h2><p className="mt-1 text-sm text-[var(--ink-muted)]">Uses the existing controlled Agent and its SQL/RAG/citation contracts for this visible pair and week.</p></div>{status === "running" ? <button type="button" onClick={() => controllerRef.current?.abort()} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line)] px-4 py-2 text-sm font-semibold"><CircleStop size={16} />Stop</button> : <button type="button" onClick={() => void generate()} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white"><Sparkles size={16} />Generate summary</button>}</div>{status === "running" ? <p role="status" className="mt-4 text-sm text-[var(--ink-muted)]">Calculating and retrieving grounded evidence…</p> : null}{status === "cancelled" ? <p className="mt-4 text-sm text-[var(--ink-muted)]">Comparison summary generation was stopped.</p> : null}{error ? <p role="alert" className="mt-4 text-sm font-medium text-[var(--danger)]">{error}</p> : null}{answer ? <p className="mt-5 whitespace-pre-wrap break-words text-sm leading-6">{answer}</p> : null}{citations.length ? <div className="mt-5 grid gap-4 lg:grid-cols-2">{citations.map((citation) => <EvidenceCard key={citation.mention_id} citation={citation} />)}</div> : null}</section>;
}
