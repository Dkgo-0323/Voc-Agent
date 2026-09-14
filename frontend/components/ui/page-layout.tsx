import type { ReactNode } from "react";

export function PageLayout({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 lg:px-10 lg:py-10">{children}</div>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="flex flex-col gap-5 border-b border-[var(--line)] pb-7 sm:flex-row sm:items-end sm:justify-between"><div className="max-w-2xl">{eyebrow ? <p className="mb-2 text-xs font-semibold uppercase tracking-[0.15em] text-[var(--brand)]">{eyebrow}</p> : null}<h1 className="text-3xl font-semibold tracking-tight text-[var(--ink)] sm:text-4xl">{title}</h1><p className="mt-3 text-sm leading-6 text-[var(--ink-muted)] sm:text-base">{description}</p></div>{actions ? <div className="shrink-0">{actions}</div> : null}</header>;
}

export function Surface({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow)] ${className}`}>{children}</section>;
}
