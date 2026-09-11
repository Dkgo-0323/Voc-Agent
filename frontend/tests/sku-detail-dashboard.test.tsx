import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SkuDetailDashboard } from "@/components/sku/sku-detail-dashboard";

const dashboardApi = vi.hoisted(() => ({ fetchSkus: vi.fn(), fetchWeeks: vi.fn(), fetchSkuDetail: vi.fn(), fetchSkuTrends: vi.fn(), fetchSkuEvidence: vi.fn() }));

vi.mock("@/lib/api/dashboard", () => dashboardApi);

const lockedSkuCodes = ["ecoflow-delta2", "jackery-explorer-1000", "jackery-explorer-240", "jackery-explorer-300", "anker-solix-f2000"];

const skus = lockedSkuCodes.map((skuCode, index) => ({ sku_code: skuCode, brand: index === 4 ? "Anker" : index ? "Jackery" : "EcoFlow", model: skuCode.replaceAll("-", " "), capacity_wh: 1000, capacity_tier: index === 4 ? "large" : index > 1 ? "entry" : "mid", is_competitor: index > 0, dashboard_enabled: true }));
const weeks = [{ week_id: 202403, week_start: "2024-01-15", week_end: "2024-01-21", doc_count: 12, mention_count: 20, skus_covered: lockedSkuCodes }];

function detail(skuCode: string) {
  return { ...skus.find((sku) => sku.sku_code === skuCode)!, week_id: 202403, review_count: 12, mention_count: 20, sentiment_breakdown: { positive: 12, negative: 5, neutral: 3 }, top_aspects: [{ aspect_label: "battery_capacity", mention_count: 10, positive_rate: 0.8 }] };
}

const citation = { mention_id: "00000000-0000-0000-0000-000000000101", document_id: "00000000-0000-0000-0000-000000000201", evidence_preview: "It lasted through the whole weekend.", sku_code: "ecoflow-delta2", aspect_label: "battery_capacity", sentiment: "positive" as const, week_id: 202403, source: { document_id: "00000000-0000-0000-0000-000000000201", sku_code: "ecoflow-delta2", platform: "amazon", published_at: "2024-01-20T00:00:00Z", source_url: "https://example.test/review", title: "Excellent battery", rating: 5, review_text: "It lasted through the whole weekend." } };

function renderDashboard(skuCode = "ecoflow-delta2") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><SkuDetailDashboard skuCode={skuCode} /></QueryClientProvider>);
}

describe("SkuDetailDashboard", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    Object.values(dashboardApi).forEach((mock) => mock.mockReset());
    dashboardApi.fetchSkus.mockResolvedValue(skus);
    dashboardApi.fetchWeeks.mockResolvedValue(weeks);
    dashboardApi.fetchSkuDetail.mockImplementation((skuCode: string) => Promise.resolve(detail(skuCode)));
    dashboardApi.fetchSkuTrends.mockResolvedValue({ sku_code: "ecoflow-delta2", sku_name: "EcoFlow DELTA 2", capacity_tier: "mid", trends: [{ week_id: 202403, aspect_label: "battery_capacity", positive_count: 7, negative_count: 2, neutral_count: 1, avg_quality_score: 0.74 }] });
    dashboardApi.fetchSkuEvidence.mockImplementation((_skuCode: string, _weekId: number, sentiment: string) => Promise.resolve(sentiment === "positive" ? [citation] : []));
  });

  it.each(lockedSkuCodes)("loads each locked dashboard SKU (%s)", async (skuCode) => {
    renderDashboard(skuCode);
    await waitFor(() => expect(dashboardApi.fetchSkuDetail).toHaveBeenCalledWith(skuCode, 202403));
    expect(await screen.findByRole("heading", { name: new RegExp(detail(skuCode).model, "i") })).toBeInTheDocument();
  });

  it("renders traceable evidence and a stateless Ask CTA", async () => {
    renderDashboard();
    expect(await screen.findByText("It lasted through the whole weekend.")).toBeInTheDocument();
    expect(screen.getByText("amazon · Jan 20, 2024 · 5/5")).toBeInTheDocument();
    expect(screen.getByText(/Evidence ID:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ask about this SKU" })).toHaveAttribute("href", "/ask");
  });

  it("renders an invalid SKU state without issuing SKU-detail reads", async () => {
    renderDashboard("not-a-sku");
    expect(await screen.findByText("SKU unavailable")).toBeInTheDocument();
    expect(dashboardApi.fetchSkuDetail).not.toHaveBeenCalled();
  });

  it("renders an empty state when the SKU has no covered weeks", async () => {
    dashboardApi.fetchWeeks.mockResolvedValue([]);
    renderDashboard();
    expect(await screen.findByText("No weekly data is available")).toBeInTheDocument();
  });

  it("renders loading and error states", async () => {
    dashboardApi.fetchSkus.mockReturnValue(new Promise(() => undefined));
    renderDashboard();
    expect(screen.getByText("Loading SKU detail")).toBeInTheDocument();
    cleanup();
    dashboardApi.fetchSkus.mockResolvedValue(skus);
    dashboardApi.fetchSkuDetail.mockRejectedValue({ message: "SKU endpoint unavailable" });
    renderDashboard();
    expect(await screen.findByText("Unable to load SKU signals")).toBeInTheDocument();
  });
});
