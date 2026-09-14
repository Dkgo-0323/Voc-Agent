"use client";

import { ErrorState } from "@/components/ui/states";
import { PageLayout } from "@/components/ui/page-layout";

export default function ApplicationError({ unstable_retry }: { error: Error & { digest?: string }; unstable_retry: () => void }) {
  return <PageLayout><ErrorState title="This page could not be displayed" description="The VOC data is unchanged. Try loading this page again." action={<button type="button" onClick={unstable_retry} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /></PageLayout>;
}
