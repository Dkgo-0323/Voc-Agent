import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/providers/query-provider";

export const metadata: Metadata = {
  title: "VOC Intelligence",
  description: "Traceable weekly voice-of-customer intelligence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-[var(--canvas)] text-[var(--ink)]">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
