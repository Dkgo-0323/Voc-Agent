"use client";

import { BarChart3, ChevronRight, FileText, GitCompareArrows, MessageSquareText, PanelLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/components/auth/auth-context";

const navigation = [
  { href: "/overview", label: "Overview", icon: BarChart3 },
  { href: "/skus/ecoflow-delta2", label: "SKU detail", icon: PanelLeft },
  { href: "/compare", label: "Compare", icon: GitCompareArrows },
  { href: "/reports", label: "Weekly reports", icon: FileText },
  { href: "/ask", label: "Ask your data", icon: MessageSquareText },
];

function isActive(pathname: string, href: string) {
  return pathname === href || (href !== "/overview" && pathname.startsWith(`${href}/`));
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { logout, user } = useAuth();

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <aside className="border-b border-[var(--line)] bg-[var(--surface)] lg:min-h-screen lg:border-r lg:border-b-0">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:block lg:px-6 lg:py-7">
          <Link href="/overview" className="flex items-center gap-3" aria-label="VOC Intelligence overview">
            <span className="grid size-9 place-items-center rounded-xl bg-[var(--brand)] text-sm font-bold text-white">V</span>
            <span><span className="block text-sm font-semibold tracking-tight">VOC Intelligence</span><span className="block text-xs text-[var(--ink-muted)]">Weekly signal desk</span></span>
          </Link>
          <button type="button" onClick={logout} className="text-xs font-medium text-[var(--ink-muted)] lg:hidden">Sign out</button>
        </div>
        <nav aria-label="Primary navigation" className="overflow-x-auto px-3 pb-3 lg:px-4 lg:pb-0">
          <ul className="flex min-w-max gap-1 lg:block lg:space-y-1">
            {navigation.map(({ href, label, icon: Icon }) => {
              const active = isActive(pathname, href);
              return <li key={href}><Link href={href} className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? "bg-[var(--brand-soft)] font-semibold text-[var(--brand-strong)]" : "text-[var(--ink-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--ink)]"}`}><Icon size={17} strokeWidth={active ? 2.3 : 1.8} />{label}</Link></li>;
            })}
          </ul>
        </nav>
        <div className="hidden px-6 pt-8 lg:block"><div className="rounded-xl border border-[var(--line)] bg-[var(--canvas)] p-4"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--ink-muted)]">Signed in</p><p className="mt-2 text-sm leading-5 text-[var(--ink-muted)]">{user?.subject ?? "Session verified"}</p><button type="button" onClick={logout} className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[var(--brand)]">Sign out <ChevronRight size={15} /></button></div></div>
      </aside>
      <main className="min-w-0">{children}</main>
    </div>
  );
}
