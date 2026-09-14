"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, ChevronRight, MessageSquareText, ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { fetchOverview, fetchSkus, fetchWeeks, type OverviewResponse, type SkuMetadata, type WeekOption } from "@/lib/api/dashboard";
import { toApiError } from "@/lib/api/client";
import { PageHeader, PageLayout, Surface } from "@/components/ui/page-layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSentimentScore(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatWeekLabel(week: WeekOption) {
  const start = new Date(`${week.week_start}T00:00:00`);
  const end = new Date(`${week.week_end}T00:00:00`);
  const dateFormat = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
  return `Week ${week.week_id} · ${dateFormat.format(start)}–${dateFormat.format(end)}`;
}

function titleFromAspect(aspect: string) {
  return aspect.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Surface><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">{label}</p><p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p><p className="mt-2 text-sm text-[var(--ink-muted)]">{detail}</p></Surface>;
}

function SentimentPanel({ overview }: { overview: OverviewResponse }) {
  const { sentiment_breakdown: breakdown, total_mentions: total } = overview.summary;
  const items = [
    { label: "Positive", value: breakdown.positive, tone: "bg-[var(--brand)]" },
    { label: "Neutral", value: breakdown.neutral, tone: "bg-[#9aa8a1]" },
    { label: "Negative", value: breakdown.negative, tone: "bg-[var(--danger)]" },
  ];

  return <Surface><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Sentiment distribution</p><h2 className="mt-2 text-xl font-semibold">Mention sentiment</h2></div><BarChart3 className="text-[var(--brand)]" size={22} /></div><div className="mt-6 flex h-3 overflow-hidden rounded-full bg-[var(--surface-muted)]" aria-label="Sentiment distribution">{items.map((item) => <span key={item.label} className={item.tone} style={{ width: total ? `${(item.value / total) * 100}%` : "0%" }} />)}</div><dl className="mt-5 grid gap-4 sm:grid-cols-3">{items.map((item) => <div key={item.label}><dt className="text-sm text-[var(--ink-muted)]">{item.label}</dt><dd className="mt-1 text-lg font-semibold">{formatNumber(item.value)}</dd></div>)}</dl></Surface>;
}

function AspectList({ title, description, aspects, positive }: { title: string; description: string; aspects: OverviewResponse["top_aspects"]; positive: boolean }) {
  const Icon = positive ? ThumbsUp : ThumbsDown;
  return <Surface><div className="flex gap-3"><span className={`grid size-9 shrink-0 place-items-center rounded-lg ${positive ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "bg-[#fae9e7] text-[var(--danger)]"}`}><Icon size={18} /></span><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Aspect overview</p><h2 className="mt-1 text-lg font-semibold">{title}</h2><p className="mt-1 text-sm text-[var(--ink-muted)]">{description}</p></div></div>{aspects.length ? <ul className="mt-5 space-y-3">{aspects.map((aspect) => <li key={aspect.aspect_label} className="flex items-center justify-between gap-4 border-t border-[var(--line)] pt-3"><div><p className="font-medium">{titleFromAspect(aspect.aspect_label)}</p><p className="mt-1 text-xs text-[var(--ink-muted)]">{formatNumber(aspect.mention_count)} mentions</p></div><span className="text-sm font-semibold text-[var(--brand-strong)]">{formatPercent(aspect.positive_rate)} positive</span></li>)}</ul> : <p className="mt-5 border-t border-[var(--line)] pt-4 text-sm text-[var(--ink-muted)]">No aspects meet this view’s available sentiment signal.</p>}</Surface>;
}

function SkuCards({ skus, overview }: { skus: SkuMetadata[]; overview: OverviewResponse }) {
  const rankings = new Map(overview.sku_rankings.map((ranking) => [ranking.sku_code, ranking]));
  return <section className="mt-8"><div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand)]">SKU monitoring</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">Covered products</h2></div><p className="text-sm text-[var(--ink-muted)]">Open a SKU for its trends and evidence.</p></div><div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{skus.map((sku) => { const ranking = rankings.get(sku.sku_code); return <Link key={sku.sku_code} href={`/skus/${sku.sku_code}`} className="group rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow)] transition-colors hover:border-[var(--brand)]"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">{sku.capacity_tier ?? "Unclassified"} tier</p><h3 className="mt-2 text-lg font-semibold">{sku.brand} {sku.model}</h3>{sku.capacity_wh ? <p className="mt-1 text-sm text-[var(--ink-muted)]">{formatNumber(sku.capacity_wh)} Wh</p> : null}</div><ChevronRight className="mt-1 text-[var(--ink-muted)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--brand)]" size={20} /></div><div className="mt-5 grid grid-cols-2 gap-3 border-t border-[var(--line)] pt-4"><div><p className="text-xs text-[var(--ink-muted)]">Mentions</p><p className="mt-1 font-semibold">{ranking ? formatNumber(ranking.mention_count) : "—"}</p></div><div><p className="text-xs text-[var(--ink-muted)]">Sentiment score</p><p className="mt-1 font-semibold">{ranking ? formatSentimentScore(ranking.sentiment_score) : "—"}</p></div></div></Link>; })}</div></section>;
}

export function OverviewDashboard() {
  const [selectedWeekId, setSelectedWeekId] = useState<number | null>(null);
  const weeksQuery = useQuery({ queryKey: ["weeks"], queryFn: fetchWeeks });
  const skusQuery = useQuery({ queryKey: ["skus"], queryFn: fetchSkus });
  const activeWeekId = selectedWeekId ?? weeksQuery.data?.[0]?.week_id;
  const overviewQuery = useQuery({ queryKey: ["overview", activeWeekId], queryFn: () => fetchOverview(activeWeekId as number), enabled: activeWeekId !== undefined });

  const retry = () => {
    void weeksQuery.refetch();
    void skusQuery.refetch();
    void overviewQuery.refetch();
  };

  if (weeksQuery.isPending) {
    return <PageLayout><PageHeader eyebrow="Portfolio monitoring" title="Overview" description="Monitor the covered week, portfolio sentiment, and SKU signals." /><div className="mt-7"><LoadingState title="Loading covered weeks" /></div></PageLayout>;
  }

  if (weeksQuery.isError || skusQuery.isError || overviewQuery.isError) {
    const queryError = weeksQuery.error ?? skusQuery.error ?? overviewQuery.error;
    return <PageLayout><PageHeader eyebrow="Portfolio monitoring" title="Overview" description="Monitor the covered week, portfolio sentiment, and SKU signals." /><div className="mt-7"><ErrorState title="Unable to load the overview" description={toApiError(queryError).message} action={<button type="button" onClick={retry} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /></div></PageLayout>;
  }

  if (!weeksQuery.data?.length || !skusQuery.data?.length) {
    return <PageLayout><PageHeader eyebrow="Portfolio monitoring" title="Overview" description="Monitor the covered week, portfolio sentiment, and SKU signals." /><div className="mt-7"><EmptyState title="No dashboard data is available" description="Run the supported enrichment pipeline before viewing portfolio signals." /></div></PageLayout>;
  }

  if (overviewQuery.isPending || !overviewQuery.data || activeWeekId === undefined) {
    return <PageLayout><PageHeader eyebrow="Portfolio monitoring" title="Overview" description="Monitor the covered week, portfolio sentiment, and SKU signals." /><div className="mt-7"><LoadingState title="Loading portfolio signals" /></div></PageLayout>;
  }

  const overview = overviewQuery.data;
  const positiveAspects = overview.top_aspects.filter((aspect) => aspect.positive_rate >= 0.5);
  const negativeAspects = overview.top_aspects.filter((aspect) => aspect.positive_rate < 0.5);
  const selectedWeek = weeksQuery.data.find((week) => week.week_id === activeWeekId);

  return <PageLayout><PageHeader eyebrow="Portfolio monitoring" title="Overview" description="A weekly view of review volume, sentiment, and the dashboard-enabled SKUs." actions={<label className="block"><span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Covered week</span><select aria-label="Covered week" value={activeWeekId} onChange={(event) => setSelectedWeekId(Number(event.target.value))} className="mt-2 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm font-medium text-[var(--ink)] sm:w-72">{weeksQuery.data.map((week) => <option key={week.week_id} value={week.week_id}>{formatWeekLabel(week)}</option>)}</select></label>} /><div className="mt-7"><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"><MetricCard label="Review volume" value={formatNumber(selectedWeek?.doc_count ?? 0)} detail="Source reviews covered this week" /><MetricCard label="Aspect mentions" value={formatNumber(overview.summary.total_mentions)} detail="Quality-qualified mentions in the portfolio" /><MetricCard label="SKUs covered" value={formatNumber(selectedWeek?.skus_covered.length ?? 0)} detail="Dashboard-enabled products with weekly data" /></div><div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]"><SentimentPanel overview={overview} /><div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-1"><AspectList title="Positive signals" description="Aspects with a majority-positive rate in this week’s overview." aspects={positiveAspects} positive /><AspectList title="Needs attention" description="Aspects below a majority-positive rate in this week’s overview." aspects={negativeAspects} positive={false} /></div></div><SkuCards skus={skusQuery.data} overview={overview} /><div className="mt-8 rounded-xl border border-[var(--line)] bg-[var(--brand-soft)] p-5 sm:flex sm:items-center sm:justify-between sm:gap-6"><div><p className="text-sm font-semibold">Need a deeper answer?</p><p className="mt-1 text-sm text-[var(--ink-muted)]">Ask the controlled Agent for a grounded metric or customer example.</p></div><Link href="/ask" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white sm:mt-0"><MessageSquareText size={16} />Ask your data</Link></div></div></PageLayout>;
}
