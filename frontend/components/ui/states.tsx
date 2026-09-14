import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

type StateProps = { title: string; description: string; action?: ReactNode };

function StateFrame({ children, title, description, action }: StateProps & { children: ReactNode }) {
  return <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface)] px-6 py-10 text-center">{children}<h2 className="mt-4 text-base font-semibold">{title}</h2><p className="mt-2 max-w-md text-sm leading-6 text-[var(--ink-muted)]">{description}</p>{action ? <div className="mt-5">{action}</div> : null}</div>;
}

export function LoadingState({ title = "Loading data" }: { title?: string }) {
  return <StateFrame title={title} description="Fetching the latest available VOC data."><LoaderCircle className="animate-spin text-[var(--brand)]" size={28} /></StateFrame>;
}

export function EmptyState({ title, description, action }: StateProps) {
  return <StateFrame title={title} description={description} action={action}><Inbox className="text-[var(--ink-muted)]" size={28} /></StateFrame>;
}

export function ErrorState({ title = "Something went wrong", description, action }: StateProps) {
  return <StateFrame title={title} description={description} action={action}><AlertCircle className="text-[var(--danger)]" size={28} /></StateFrame>;
}
