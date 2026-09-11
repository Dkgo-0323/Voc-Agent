"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-context";
import { LoadingState } from "@/components/ui/states";
import { PageLayout } from "@/components/ui/page-layout";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [router, status]);

  if (status === "authenticated") {
    return children;
  }

  return <PageLayout><LoadingState title={status === "error" ? "Unable to verify your session" : "Checking your session"} /></PageLayout>;
}
