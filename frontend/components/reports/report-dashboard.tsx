"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleStop, FileText, RefreshCw, Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { PageHeader, PageLayout, Surface } from "@/components/ui/page-layout";
import { toApiError } from "@/lib/api/client";
import { fetchSkus, fetchWeeks, type SkuMetadata } from "@/lib/api/dashboard";
import { fetchWeeklyReport, streamReportGeneration, type ReportStreamEvent, type WeeklyReport } from "@/lib/api/reports";

const stageLabels: Record<string, string> = {
  collecting_analytics: "Calculating verified weekly metrics…",
  retrieving_evidence: "Reviewing representative customer evidence…",
  synthesizing: "Drafting the weekly report…",
  validating: "Checking report structure and supported content…",
  persisting: "Saving the validated report…",
};

function formatWeek(weekId: number) {
  const year = Math.floor(weekId / 100);
  return `${year} W${String(weekId % 100).padStart(2, "0")}`;
}

function formatGeneratedAt(value: string) {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function MarkdownReport({ markdown }: { markdown: string }) {
  return <div className="space-y-5">{markdown.split("\n\n").filter(Boolean).map((block, index) => {
    const lines = block.split("\n");
    if (block.startsWith("## ")) {
      return <section key={`${block.slice(0, 24)}-${index}`}><h2 className="text-xl font-semibold tracking-tight">{lines[0].slice(3)}</h2>{lines.slice(1).filter(Boolean).map((line, lineIndex) => <p key={lineIndex} className="mt-2 text-sm leading-6 text-[var(--ink-muted)]">{line}</p>)}</section>;
    }
    if (lines.every((line) => line.startsWith("- "))) {
      return <ul key={index} className="list-disc space-y-2 pl-5 text-sm leading-6 text-[var(--ink-muted)]">{lines.map((line) => <li key={line}>{line.slice(2)}</li>)}</ul>;
    }
    return <p key={index} className="text-sm leading-6 text-[var(--ink-muted)]">{block}</p>;
  })}</div>;
}

function ReportView({ report, sku }: { report: WeeklyReport; sku: SkuMetadata | undefined }) {
  return <div className="mt-6 space-y-5"><Surface><div className="flex flex-col gap-4 border-b border-[var(--line)] pb-5 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand)]">Persisted weekly report</p><h2 className="mt-2 text-2xl font-semibold">{sku ? `${sku.brand} ${sku.model}` : report.sku_code}</h2><p className="mt-1 text-sm text-[var(--ink-muted)]">{formatWeek(report.week_id)} · Saved {formatGeneratedAt(report.generated_at)}</p></div><FileText className="text-[var(--brand)]" size={24} /></div>{report.summary ? <p className="mt-5 text-base leading-7 text-[var(--ink)]">{report.summary}</p> : null}<div className="mt-6 border-t border-[var(--line)] pt-6">{report.report_md ? <MarkdownReport markdown={report.report_md} /> : <p className="text-sm text-[var(--ink-muted)]">This stored report has no Markdown body.</p>}</div></Surface><Surface><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Evidence and citations</p><h2 className="mt-2 text-lg font-semibold">Report citation availability</h2><p className="mt-2 text-sm leading-6 text-[var(--ink-muted)]">This report was generated from filtered evidence, but the current persisted report contract does not store report-to-mention links. Citation cards are therefore unavailable here rather than being inferred or fabricated.</p></Surface></div>;
}

export function ReportDashboard() {
  const queryClient = useQueryClient();
  const [selectedWeek, setSelectedWeek] = useState<number | null>(null);
  const [selectedSku, setSelectedSku] = useState("");
  const [completedReport, setCompletedReport] = useState<WeeklyReport | null>(null);
  const [generationState, setGenerationState] = useState<"idle" | "running" | "error">("idle");
  const [generationScope, setGenerationScope] = useState<string | null>(null);
  const [progress, setProgress] = useState("Preparing report generation…");
  const [generationError, setGenerationError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const weeksQuery = useQuery({ queryKey: ["weeks"], queryFn: fetchWeeks });
  const skusQuery = useQuery({ queryKey: ["skus"], queryFn: fetchSkus });
  const weekId = selectedWeek ?? weeksQuery.data?.[0]?.week_id;
  const skuCode = selectedSku || skusQuery.data?.[0]?.sku_code;
  const reportQuery = useQuery({ queryKey: ["weekly-report", skuCode, weekId], queryFn: () => fetchWeeklyReport(skuCode as string, weekId as number), enabled: Boolean(skuCode && weekId), retry: false });

  const scopeKey = skuCode && weekId ? `${skuCode}:${weekId}` : null;
  const activeGeneration = generationState === "running" && generationScope === scopeKey;
  const isGenerating = generationState === "running";
  const visibleReport = completedReport?.sku_code === skuCode && completedReport?.week_id === weekId ? completedReport : reportQuery.data;
  const isMissing = reportQuery.isError && toApiError(reportQuery.error).status === 404;
  const selectedSkuMetadata = skusQuery.data?.find((sku) => sku.sku_code === skuCode);

  const startGeneration = async () => {
    if (!skuCode || !weekId || isGenerating) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setGenerationScope(`${skuCode}:${weekId}`); setGenerationState("running"); setGenerationError(""); setProgress("Preparing report generation…");
    let streamError = "";
    let terminalEventReceived = false;
    try {
      await streamReportGeneration({ sku_code: skuCode, week_id: weekId }, (event: ReportStreamEvent) => {
        if (event.event_type === "stage_started") setProgress(stageLabels[event.stage] ?? "Generating report…");
        if (event.event_type === "stage_completed" && event.warnings.length) setProgress("Continuing with available weekly evidence…");
        if (event.event_type === "report_delta") setProgress("Validated draft is ready; saving the report…");
        if (event.event_type === "report_completed") {
          terminalEventReceived = true;
          setCompletedReport(event.report);
          queryClient.setQueryData(["weekly-report", skuCode, weekId], event.report);
          setProgress("Report saved.");
        }
        if (event.event_type === "error") { terminalEventReceived = true; streamError = event.error.message; }
      }, { signal: controller.signal });
      if (streamError || !terminalEventReceived) { setGenerationError(streamError || "The report stream ended before the report was saved. Please try again."); setGenerationState("error"); } else setGenerationState("idle");
    } catch (caught) {
      setGenerationError(controller.signal.aborted ? "Report generation was stopped. The saved report was not changed." : toApiError(caught).message); setGenerationState("error");
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  };

  const cancelGeneration = () => controllerRef.current?.abort();

  if (weeksQuery.isPending || skusQuery.isPending) return <PageLayout><PageHeader eyebrow="Weekly intelligence" title="Reports" description="View a saved weekly report or explicitly generate a new one." /><div className="mt-7"><LoadingState title="Loading report choices" /></div></PageLayout>;
  if (weeksQuery.isError || skusQuery.isError) return <PageLayout><PageHeader eyebrow="Weekly intelligence" title="Reports" description="View a saved weekly report or explicitly generate a new one." /><div className="mt-7"><ErrorState title="Unable to load report choices" description={toApiError(weeksQuery.error ?? skusQuery.error).message} action={<button type="button" onClick={() => { void weeksQuery.refetch(); void skusQuery.refetch(); }} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /></div></PageLayout>;
  if (!weekId || !skuCode) return <PageLayout><PageHeader eyebrow="Weekly intelligence" title="Reports" description="View a saved weekly report or explicitly generate a new one." /><div className="mt-7"><EmptyState title="No report scope is available" description="Run the supported enrichment pipeline before generating weekly reports." /></div></PageLayout>;
  const reportError = reportQuery.isError && !isMissing ? toApiError(reportQuery.error) : null;

  return <PageLayout><PageHeader eyebrow="Weekly intelligence" title="Reports" description="Reports are generated only when you explicitly request them, then shown after the backend confirms persistence." actions={<div className="grid gap-3 sm:grid-cols-2"><label><span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">SKU</span><select aria-label="Report SKU" value={skuCode} disabled={isGenerating} onChange={(event) => setSelectedSku(event.target.value)} className="mt-2 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60">{skusQuery.data?.map((sku) => <option key={sku.sku_code} value={sku.sku_code}>{sku.brand} {sku.model}</option>)}</select></label><label><span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Covered week</span><select aria-label="Report week" value={weekId} disabled={isGenerating} onChange={(event) => setSelectedWeek(Number(event.target.value))} className="mt-2 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60">{weeksQuery.data?.map((week) => <option key={week.week_id} value={week.week_id}>{formatWeek(week.week_id)}</option>)}</select></label></div>} /><div className="mt-7">{reportQuery.isPending && !visibleReport ? <LoadingState title="Looking for a saved report" /> : null}{reportError ? <ErrorState title="Unable to load the report" description={reportError.message} action={<button type="button" onClick={() => void reportQuery.refetch()} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /> : null}{isMissing && !visibleReport ? <EmptyState title="No report has been generated" description="Generate a bounded weekly report for this SKU and covered week when you are ready." action={<button type="button" onClick={() => void startGeneration()} disabled={isGenerating} className="inline-flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70"><Sparkles size={16} />Generate report</button>} /> : null}{visibleReport ? <><div className="flex flex-col gap-4 rounded-xl border border-[var(--line)] bg-[var(--brand-soft)] p-5 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-semibold">{activeGeneration ? "Regenerating report" : "Weekly report available"}</p><p className="mt-1 text-sm text-[var(--ink-muted)]">{activeGeneration ? "The saved report remains visible until a validated replacement is committed." : "Generate again only when you want a refreshed report."}</p></div><button type="button" onClick={() => void startGeneration()} disabled={isGenerating} className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70"><RefreshCw size={16} />{activeGeneration ? "Regenerating…" : "Regenerate report"}</button></div><ReportView report={visibleReport} sku={selectedSkuMetadata} /></> : null}{activeGeneration ? <Surface className="mt-5"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand)]">Report generation</p><p role="status" className="mt-2 text-lg font-semibold">{progress}</p><p className="mt-2 text-sm leading-6 text-[var(--ink-muted)]">Only a successfully saved report replaces the report shown above.</p><button type="button" onClick={cancelGeneration} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-[var(--line)] px-4 py-2 text-sm font-semibold"><CircleStop size={16} />Stop generation</button></Surface> : null}{generationError && generationScope === scopeKey ? <div className="mt-5"><ErrorState title="Report generation did not complete" description={generationError} action={<button type="button" onClick={() => void startGeneration()} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Retry generation</button>} /></div> : null}</div></PageLayout>;
}
