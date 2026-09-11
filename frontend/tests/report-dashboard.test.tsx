import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReportDashboard } from "@/components/reports/report-dashboard";

const dashboardApi = vi.hoisted(() => ({ fetchWeeks: vi.fn(), fetchSkus: vi.fn() }));
const reportsApi = vi.hoisted(() => ({ fetchWeeklyReport: vi.fn(), streamReportGeneration: vi.fn() }));
vi.mock("@/lib/api/dashboard", () => dashboardApi);
vi.mock("@/lib/api/reports", () => reportsApi);

const weeks = [{ week_id: 202403, week_start: "2024-01-15", week_end: "2024-01-21", doc_count: 12, mention_count: 20, skus_covered: ["ecoflow-delta2"] }];
const skus = [{ sku_code: "ecoflow-delta2", brand: "EcoFlow", model: "DELTA 2", capacity_wh: 1024, capacity_tier: "mid", is_competitor: false, dashboard_enabled: true }];
const report = { report_id: "00000000-0000-0000-0000-000000000301", sku_code: "ecoflow-delta2", week_id: 202403, summary: "A persisted summary from the weekly report.", report_md: "## Executive Summary\nWeekly feedback is stable.\n\n## Key Metrics\nTwelve reviews were included.\n\n## Positive Themes\nBattery capacity is noted.\n\n## Negative Themes\nCharging remains a concern.\n\n## SKU Highlights\nThe SKU is monitored.\n\n## Competitor Observations\nNo comparison data was supplied.", generated_at: "2024-01-22T09:30:00Z" };

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ReportDashboard /></QueryClientProvider>);
}

describe("ReportDashboard", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    dashboardApi.fetchWeeks.mockReset(); dashboardApi.fetchSkus.mockReset(); reportsApi.fetchWeeklyReport.mockReset(); reportsApi.streamReportGeneration.mockReset();
    dashboardApi.fetchWeeks.mockResolvedValue(weeks); dashboardApi.fetchSkus.mockResolvedValue(skus); reportsApi.fetchWeeklyReport.mockResolvedValue(report);
  });

  it("renders an existing persisted report without starting generation on load", async () => {
    renderDashboard();

    expect(await screen.findByText("A persisted summary from the weekly report.")).toBeInTheDocument();
    expect(screen.getByText("Report citation availability")).toBeInTheDocument();
    expect(reportsApi.streamReportGeneration).not.toHaveBeenCalled();
  });

  it("shows a no-report state and only generates after the explicit action", async () => {
    reportsApi.fetchWeeklyReport.mockRejectedValue({ status: 404, message: "Missing report" });
    reportsApi.streamReportGeneration.mockImplementation(async (_payload: unknown, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "stage_started", stage: "collecting_analytics" });
      onEvent({ event_type: "report_delta", delta: "uncommitted candidate" });
      onEvent({ event_type: "report_completed", report });
    });
    renderDashboard();

    expect(await screen.findByText("No report has been generated")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Generate report" }));
    await waitFor(() => expect(reportsApi.streamReportGeneration).toHaveBeenCalledWith({ sku_code: "ecoflow-delta2", week_id: 202403 }, expect.any(Function)));
    expect(await screen.findByText("A persisted summary from the weekly report.")).toBeInTheDocument();
    expect(screen.queryByText("uncommitted candidate")).not.toBeInTheDocument();
  });

  it("keeps the old report visible when regeneration fails and offers retry", async () => {
    reportsApi.streamReportGeneration.mockImplementation(async (_payload: unknown, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "stage_started", stage: "retrieving_evidence" });
      onEvent({ event_type: "error", error: { code: "report_retrieval_failed", message: "Evidence retrieval is temporarily unavailable.", retryable: true } });
    });
    renderDashboard();
    await screen.findByText("A persisted summary from the weekly report.");

    fireEvent.click(screen.getByRole("button", { name: "Regenerate report" }));
    expect(await screen.findByText("Report generation did not complete")).toBeInTheDocument();
    expect(screen.getByText("A persisted summary from the weekly report.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry generation" })).toBeInTheDocument();
  });
});
