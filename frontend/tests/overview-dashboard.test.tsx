import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OverviewDashboard } from "@/components/overview/overview-dashboard";

const dashboardApi = vi.hoisted(() => ({
  fetchWeeks: vi.fn(),
  fetchOverview: vi.fn(),
  fetchSkus: vi.fn(),
}));

vi.mock("@/lib/api/dashboard", () => dashboardApi);

const weeks = [
  { week_id: 202403, week_start: "2024-01-15", week_end: "2024-01-21", doc_count: 12, mention_count: 20, skus_covered: ["ecoflow-delta2", "jackery-explorer-1000"] },
  { week_id: 202402, week_start: "2024-01-08", week_end: "2024-01-14", doc_count: 8, mention_count: 14, skus_covered: ["ecoflow-delta2"] },
];

const skus = [
  { sku_code: "ecoflow-delta2", brand: "EcoFlow", model: "DELTA 2", capacity_wh: 1024, capacity_tier: "mid", is_competitor: false, dashboard_enabled: true },
  { sku_code: "jackery-explorer-1000", brand: "Jackery", model: "Explorer 1000", capacity_wh: 1002, capacity_tier: "mid", is_competitor: true, dashboard_enabled: true },
];

function overview(weekId: number) {
  return {
    week_id: weekId,
    summary: { total_mentions: weekId === 202403 ? 20 : 14, sentiment_breakdown: { positive: 10, negative: 4, neutral: 6 } },
    top_aspects: [
      { aspect_label: "battery_capacity", mention_count: 9, positive_rate: 0.78 },
      { aspect_label: "noise", mention_count: 5, positive_rate: 0.2 },
    ],
    sku_rankings: [
      { sku_code: "ecoflow-delta2", sku_name: "EcoFlow DELTA 2", mention_count: 11, sentiment_score: 0.5 },
      { sku_code: "jackery-explorer-1000", sku_name: "Jackery Explorer 1000", mention_count: 9, sentiment_score: 0.2 },
    ],
  };
}

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><OverviewDashboard /></QueryClientProvider>);
}

describe("OverviewDashboard", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    dashboardApi.fetchWeeks.mockReset();
    dashboardApi.fetchSkus.mockReset();
    dashboardApi.fetchOverview.mockReset();
    dashboardApi.fetchWeeks.mockResolvedValue(weeks);
    dashboardApi.fetchSkus.mockResolvedValue(skus);
    dashboardApi.fetchOverview.mockImplementation((weekId: number) => Promise.resolve(overview(weekId)));
  });

  it("uses the covered week for the overview query and renders real API metrics", async () => {
    renderDashboard();

    expect(await screen.findByRole("heading", { name: "Covered products" })).toBeInTheDocument();
    expect(dashboardApi.fetchOverview).toHaveBeenCalledWith(202403);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Battery Capacity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /EcoFlow DELTA 2/i })).toHaveAttribute("href", "/skus/ecoflow-delta2");

    fireEvent.change(screen.getByLabelText("Covered week"), { target: { value: "202402" } });
    await waitFor(() => expect(dashboardApi.fetchOverview).toHaveBeenCalledWith(202402));
  });

  it("shows an empty state when no covered weeks exist", async () => {
    dashboardApi.fetchWeeks.mockResolvedValue([]);
    renderDashboard();

    expect(await screen.findByText("No dashboard data is available")).toBeInTheDocument();
  });

  it("shows a retryable error state for a failed dashboard read", async () => {
    dashboardApi.fetchOverview.mockRejectedValue({ message: "Dashboard unavailable" });
    renderDashboard();

    expect(await screen.findByText("Unable to load the overview")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
