"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-context";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { PageLayout } from "@/components/ui/page-layout";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { retryBootstrap, status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [router, status]);

  if (status === "authenticated") {
    return children;
  }

  if (status === "error") {
    return <PageLayout><ErrorState title="Unable to verify your session" description="Check your connection and try again. Your session has not been restored." action={<button type="button" onClick={() => void retryBootstrap()} className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white">Try again</button>} /></PageLayout>;
  }

  return <PageLayout><LoadingState title="Checking your session" /></PageLayout>;
}
