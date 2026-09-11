import { publicApiClient } from "@/lib/api/client";

export type WeekOption = {
  week_id: number;
  week_start: string;
  week_end: string;
  doc_count: number;
  mention_count: number;
  skus_covered: string[];
};

export type OverviewResponse = {
  week_id: number;
  summary: {
    total_mentions: number;
    sentiment_breakdown: {
      positive: number;
      negative: number;
      neutral: number;
    };
  };
  top_aspects: Array<{
    aspect_label: string;
    mention_count: number;
    positive_rate: number;
  }>;
  sku_rankings: Array<{
    sku_code: string;
    sku_name: string;
    mention_count: number;
    sentiment_score: number;
  }>;
};

export type SkuMetadata = {
  sku_code: string;
  brand: string;
  model: string;
  capacity_wh: number | null;
  capacity_tier: string | null;
  is_competitor: boolean;
  dashboard_enabled: boolean;
};

export async function fetchWeeks(): Promise<WeekOption[]> {
  const response = await publicApiClient.get<WeekOption[]>("/api/weeks");
  return response.data;
}

export async function fetchOverview(weekId: number): Promise<OverviewResponse> {
  const response = await publicApiClient.get<OverviewResponse>("/api/overview", {
    params: { week_id: weekId },
  });
  return response.data;
}

export async function fetchSkus(): Promise<SkuMetadata[]> {
  const response = await publicApiClient.get<SkuMetadata[]>("/api/skus");
  return response.data;
}
