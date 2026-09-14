"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MessageSquareText, ThumbsDown, ThumbsUp, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EvidenceCard } from "@/components/evidence/evidence-card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { PageHeader, PageLayout, Surface } from "@/components/ui/page-layout";
import { fetchSkuDetail, fetchSkuEvidence, fetchSkus, fetchSkuTrends, fetchWeeks, type SkuDetailResponse, type TrendPoint, type WeekOption } from "@/lib/api/dashboard";
import { toApiError } from "@/lib/api/client";

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value: number) {
  return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 }).format(value);
}

function formatWeek(weekId: number) {
  const year = Math.floor(weekId / 100);
  const week = weekId % 100;
  return `${year} W${String(week).padStart(2, "0")}`;
}

function titleFromAspect(aspect: string) {
  return aspect.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <Surface><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">{label}</p><p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p><p className="mt-2 text-sm text-[var(--ink-muted)]">{detail}</p></Surface>;
}

function SentimentDistribution({ detail }: { detail: SkuDetailResponse }) {
  const total = detail.mention_count;
  const values = [
    { label: "Positive", count: detail.sentiment_breakdown.positive, tone: "bg-[var(--brand)]" },
    { label: "Neutral", count: detail.sentiment_breakdown.neutral, tone: "bg-[#9aa8a1]" },
    { label: "Negative", count: detail.sentiment_breakdown.negative, tone: "bg-[var(--danger)]" },
  ];
  return <Surface><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Sentiment distribution</p><h2 className="mt-2 text-xl font-semibold">Mention sentiment</h2><div className="mt-6 flex h-3 overflow-hidden rounded-full bg-[var(--surface-muted)]" aria-label="Sentiment distribution">{values.map((item) => <span key={item.label} className={item.tone} style={{ width: total ? `${(item.count / total) * 100}%` : "0%" }} />)}</div><dl className="mt-5 grid gap-4 sm:grid-cols-3">{values.map((item) => <div key={item.label}><dt className="text-sm text-[var(--ink-muted)]">{item.label}</dt><dd className="mt-1 text-lg font-semibold">{formatNumber(item.count)}</dd></div>)}</dl></Surface>;
}

function AspectDistribution({ detail }: { detail: SkuDetailResponse }) {
  return <Surface><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Aspect distribution</p><h2 className="mt-2 text-xl font-semibold">Top mentioned aspects</h2>{detail.top_aspects.length ? <ul className="mt-5 space-y-3">{detail.top_aspects.map((aspect) => <li key={aspect.aspect_label} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 border-t border-[var(--line)] pt-3"><div><p className="font-medium">{titleFromAspect(aspect.aspect_label)}</p><p className="mt-1 text-xs text-[var(--ink-muted)]">{formatNumber(aspect.mention_count)} mentions</p></div><span className="text-sm font-semibold text-[var(--brand-strong)]">{formatPercent(aspect.positive_rate)} positive</span></li>)}</ul> : <p className="mt-5 border-t border-[var(--line)] pt-4 text-sm text-[var(--ink-muted)]">No quality-qualified aspect data is available for this week.</p>}</Surface>;
}

function TrendTable({ trends }: { trends: TrendPoint[] }) {
  return <Surface className="mt-5"><div className="flex items-start gap-3"><span className="grid size-9 place-items-center rounded-lg bg-[var(--brand-soft)] text-[var(--brand)]"><TrendingUp size={18} /></span><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Historical trend</p><h2 className="mt-1 text-xl font-semibold">Recent aspect signals</h2><p className="mt-1 text-sm text-[var(--ink-muted)]">Latest backend-provided weekly trend points, up to eight weeks.</p></div></div>{trends.length ? <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[34rem] text-left text-sm"><thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.1em] text-[var(--ink-muted)]"><tr><th className="pb-3 font-semibold">Week</th><th className="pb-3 font-semibold">Aspect</th><th className="pb-3 text-right font-semibold">Positive</th><th className="pb-3 text-right font-semibold">Neutral</th><th className="pb-3 text-right font-semibold">Negative</th></tr></thead><tbody>{trends.map((trend) => <tr key={`${trend.week_id}-${trend.aspect_label}`} className="border-b border-[var(--line)] last:border-0"><td className="py-3 font-medium">{formatWeek(trend.week_id)}</td><td className="py-3">{titleFromAspect(trend.aspect_label)}</td><td className="py-3 text-right">{formatNumber(trend.positive_count)}</td><td className="py-3 text-right">{formatNumber(trend.neutral_count)}</td><td className="py-3 text-right">{formatNumber(trend.negative_count)}</td></tr>)}</tbody></table></div> : <p className="mt-5 border-t border-[var(--line)] pt-4 text-sm text-[var(--ink-muted)]">No historical trend points are available yet.</p>}</Surface>;
}

function EvidenceSection({ title, description, citations, positive }: { title: string; description: string; citations: Awaited<ReturnType<typeof fetchSkuEvidence>>; positive: boolean }) {
  const Icon = positive ? ThumbsUp : ThumbsDown;
  return <section><div className="flex items-start gap-3"><span className={`grid size-9 place-items-center rounded-lg ${positive ? "bg-[var(--brand-soft)] text-[var(--brand)]" : "bg-[#fae9e7] text-[var(--danger)]"}`}><Icon size={18} /></span><div><h2 className="text-xl font-semibold">{title}</h2><p className="mt-1 text-sm text-[var(--ink-muted)]">{description}</p></div></div>{citations.length ? <div className="mt-4 grid gap-4 lg:grid-cols-2">{citations.map((citation) => <EvidenceCard key={citation.mention_id} citation={citation} />)}</div> : <EmptyState title={`No ${title.toLowerCase()} found`} description="No quality-qualified evidence matches this sentiment for the selected week." />}</section>;
}

export function SkuDetailDashboard({ skuCode }: { skuCode: string }) {
  const [selectedWeekId, setSelectedWeekId] = useState<number | null>(null);
  const skusQuery = useQuery({ queryKey: ["skus"], queryFn: fetchSkus });
  const weeksQuery = useQuery({ queryKey: ["weeks"], queryFn: fetchWeeks });
  const knownSku = skusQuery.data?.find((sku) => sku.sku_code === skuCode);
  const skuWeeks = weeksQuery.data?.filter((week) => week.skus_covered.includes(skuCode)) ?? [];
  const activeWeekId = selectedWeekId ?? skuWeeks[0]?.week_id;
  const detailQuery = useQuery({ queryKey: ["sku-detail", skuCode, activeWeekId], queryFn: () => fetchSkuDetail(skuCode, activeWeekId as number), enabled: Boolean(knownSku) && activeWeekId !== undefined });
  const trendsQuery = useQuery({ queryKey: ["sku-trends", skuCode], queryFn: () => fetchSkuTrends(skuCode), enabled: Boolean(knownSku) });
  const positiveEvidenceQuery = useQuery({ queryKey: ["sku-evidence", skuCode, activeWeekId, "positive"], queryFn: () => fetchSkuEvidence(skuCode, activeWeekId as number, "positive"), enabled: Boolean(knownSku) && activeWeekId !== undefined });
  const negativeEvidenceQuery = useQuery({ queryKey: ["sku-evidence", skuCode, activeWeekId, "negative"], queryFn: () => fetchSkuEvidence(skuCode, activeWeekId as number, "negative"), enabled: Boolean(knownSku) && activeWeekId !== undefined });

  const retry = () => {
    void skusQuery.refetch();
    void weeksQuery.refetch();
    void detailQuery.refetch();
    void trendsQuery.refetch();
    void positiveEvidenceQuery.refetch();
    void negativeEvidenceQuery.refetch();
  };

  if (skusQuery.isPending || weeksQuery.isPending) {
    return <PageLayout><div className="mt-7"><LoadingState title="Loading SKU detail" /></div></PageLayout>;
  }

  if (skusQuery.isError || weeksQuery.isError) {
    return <PageLayout><ErrorState title="Unable to load SKU detail" description={toApiError(skusQuery.error ?? weeksQuery.error).message} action={<button type="button" onClick={retry} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /></PageLayout>;
  }

  if (!knownSku) {
    return <PageLayout><ErrorState title="SKU unavailable" description="This SKU is not enabled for the VOC dashboard." action={<Link href="/overview" className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Return to overview</Link>} /></PageLayout>;
  }

  if (!skuWeeks.length) {
    return <PageLayout><PageHeader eyebrow="SKU monitoring" title={`${knownSku.brand} ${knownSku.model}`} description="A detail view of quality-qualified VOC signals for this SKU." /><div className="mt-7"><EmptyState title="No weekly data is available" description="This dashboard-enabled SKU has no covered weeks yet." /></div></PageLayout>;
  }

  const queryError = detailQuery.error ?? trendsQuery.error ?? positiveEvidenceQuery.error ?? negativeEvidenceQuery.error;
  if (queryError) {
    return <PageLayout><ErrorState title="Unable to load SKU signals" description={toApiError(queryError).message} action={<button type="button" onClick={retry} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /></PageLayout>;
  }

  if (detailQuery.isPending || trendsQuery.isPending || positiveEvidenceQuery.isPending || negativeEvidenceQuery.isPending || !detailQuery.data) {
    return <PageLayout><div className="mt-7"><LoadingState title="Loading SKU signals" /></div></PageLayout>;
  }

  const detail = detailQuery.data;
  return <PageLayout><Link href="/overview" className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--brand-strong)]"><ArrowLeft size={16} />Back to overview</Link><PageHeader eyebrow="SKU monitoring" title={`${detail.brand} ${detail.model}`} description={`${detail.capacity_wh ? `${formatNumber(detail.capacity_wh)} Wh · ` : ""}${detail.capacity_tier ?? "Unclassified"} capacity tier · dashboard-enabled SKU`} actions={<label className="block"><span className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Covered week</span><select aria-label="Covered week" value={activeWeekId} onChange={(event) => setSelectedWeekId(Number(event.target.value))} className="mt-2 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-sm font-medium sm:w-52">{skuWeeks.map((week: WeekOption) => <option key={week.week_id} value={week.week_id}>{formatWeek(week.week_id)}</option>)}</select></label>} /><div className="mt-7"><div className="grid gap-4 md:grid-cols-3"><MetricCard label="Review volume" value={formatNumber(detail.review_count)} detail="Source reviews this week" /><MetricCard label="Aspect mentions" value={formatNumber(detail.mention_count)} detail="Quality-qualified mentions" /><MetricCard label="Capacity tier" value={detail.capacity_tier ?? "—"} detail="Server-defined comparison tier" /></div><div className="mt-5 grid gap-5 xl:grid-cols-2"><SentimentDistribution detail={detail} /><AspectDistribution detail={detail} /></div><TrendTable trends={trendsQuery.data?.trends ?? []} /><div className="mt-8 grid gap-8"><EvidenceSection title="Positive evidence" description="Traceable review evidence selected from positive mentions." citations={positiveEvidenceQuery.data ?? []} positive /><EvidenceSection title="Negative evidence" description="Traceable review evidence selected from negative mentions." citations={negativeEvidenceQuery.data ?? []} positive={false} /></div><div className="mt-8 rounded-xl border border-[var(--line)] bg-[var(--brand-soft)] p-5 sm:flex sm:items-center sm:justify-between sm:gap-6"><div><p className="text-sm font-semibold">Want a grounded answer about this SKU?</p><p className="mt-1 text-sm text-[var(--ink-muted)]">Ask the controlled Agent directly. This link does not retain any hidden SKU state.</p></div><Link href="/ask" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white sm:mt-0"><MessageSquareText size={16} />Ask about this SKU</Link></div></div></PageLayout>;
}
