import type { ReactNode } from "react";
import { PageHeader, PageLayout, Surface } from "@/components/ui/page-layout";
import { EmptyState } from "@/components/ui/states";

export function FeaturePlaceholder({ eyebrow, title, description, dataSource, children }: { eyebrow: string; title: string; description: string; dataSource: string; children?: ReactNode }) {
  return <PageLayout><PageHeader eyebrow={eyebrow} title={title} description={description} /><div className="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]"><EmptyState title="Feature workspace is ready" description="This route has its shared layout, loading, empty, and error handling foundation. Its business view arrives in a later scoped phase." /><Surface className="h-fit"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Planned data source</p><p className="mt-3 whitespace-pre-line font-mono text-xs leading-6 text-[var(--brand-strong)]">{dataSource}</p>{children ? <div className="mt-5 border-t border-[var(--line)] pt-5">{children}</div> : null}</Surface></div></PageLayout>;
}
