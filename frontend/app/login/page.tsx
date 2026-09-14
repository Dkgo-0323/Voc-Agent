"use client";

import { FormEvent, useEffect, useState } from "react";
import { LockKeyhole } from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-context";
import type { ApiError } from "@/lib/api/client";

export default function LoginPage() {
  const router = useRouter();
  const { status, login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/overview");
    }
  }, [router, status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password.trim()) {
      setError("Enter the configured password to continue.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(password);
      router.replace("/overview");
    } catch (caughtError) {
      setError((caughtError as ApiError).message);
      setSubmitting(false);
    }
  }

  return <main className="grid min-h-screen place-items-center px-5 py-10"><section className="w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-7 shadow-[var(--shadow)] sm:p-9"><div className="grid size-11 place-items-center rounded-xl bg-[var(--brand-soft)] text-[var(--brand)]"><LockKeyhole size={21} /></div><p className="mt-6 text-xs font-semibold uppercase tracking-[0.15em] text-[var(--brand)]">VOC Intelligence</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Session access</h1><p className="mt-3 text-sm leading-6 text-[var(--ink-muted)]">Sign in with the configured workspace password.</p><form className="mt-7 space-y-4" onSubmit={handleSubmit}><label className="block text-sm font-semibold" htmlFor="password">Password</label><input id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} disabled={submitting} className="w-full rounded-lg border border-[var(--line)] bg-white px-3 py-2.5 outline-none focus:border-[var(--brand)] focus:ring-2 focus:ring-[var(--brand-soft)]" />{error ? <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-[var(--danger)]">{error}</p> : null}<button type="submit" disabled={submitting || status === "loading"} className="inline-flex w-full items-center justify-center rounded-lg bg-[var(--brand)] px-4 py-3 text-sm font-semibold text-white hover:bg-[var(--brand-strong)] disabled:cursor-not-allowed disabled:opacity-60">{submitting ? "Signing in…" : "Sign in"}</button></form></section></main>;
}
