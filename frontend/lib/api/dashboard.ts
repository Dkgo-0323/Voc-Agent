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

export type Sentiment = "positive" | "negative" | "neutral";

export type SkuDetailResponse = SkuMetadata & {
  week_id: number;
  review_count: number;
  mention_count: number;
  sentiment_breakdown: {
    positive: number;
    negative: number;
    neutral: number;
  };
  top_aspects: OverviewResponse["top_aspects"];
};

export type TrendPoint = {
  week_id: number;
  aspect_label: string;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  avg_quality_score: number;
};

export type SkuTrendsResponse = {
  sku_code: string;
  sku_name: string;
  capacity_tier: string;
  trends: TrendPoint[];
};

export type EvidenceCitation = {
  mention_id: string;
  document_id: string;
  evidence_preview: string;
  sku_code: string;
  aspect_label: string;
  sentiment: Sentiment;
  week_id: number;
  source: {
    document_id: string;
    sku_code: string;
    platform: string;
    published_at: string | null;
    source_url: string | null;
    title: string | null;
    rating: number | null;
    review_text: string | null;
  };
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

export async function fetchSkuDetail(
  skuCode: string,
  weekId: number,
): Promise<SkuDetailResponse> {
  const response = await publicApiClient.get<SkuDetailResponse>(
    `/api/skus/${encodeURIComponent(skuCode)}`,
    { params: { week_id: weekId } },
  );
  return response.data;
}

export async function fetchSkuTrends(skuCode: string): Promise<SkuTrendsResponse> {
  const response = await publicApiClient.get<SkuTrendsResponse>(
    `/api/skus/${encodeURIComponent(skuCode)}/trends`,
    { params: { weeks: 8 } },
  );
  return response.data;
}

export async function fetchSkuEvidence(
  skuCode: string,
  weekId: number,
  sentiment: Extract<Sentiment, "positive" | "negative">,
): Promise<EvidenceCitation[]> {
  const response = await publicApiClient.get<EvidenceCitation[]>(
    `/api/skus/${encodeURIComponent(skuCode)}/evidence`,
    { params: { week_id: weekId, sentiment, limit: 5 } },
  );
  return response.data;
}
