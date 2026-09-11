import { AUTH_UNAUTHORIZED_EVENT, apiClient, getApiAccessToken, publicApiClient } from "@/lib/api/client";

export type WeeklyReport = {
  report_id: string;
  sku_code: string;
  week_id: number;
  report_md: string | null;
  summary: string | null;
  generated_at: string;
};

export type ReportStreamEvent =
  | { event_type: "report_started"; sku_code: string; week_id: number }
  | { event_type: "stage_started"; stage: string }
  | { event_type: "stage_completed"; stage: string; warnings: string[] }
  | { event_type: "report_delta"; delta: string }
  | { event_type: "report_completed"; report: WeeklyReport }
  | { event_type: "error"; error: { code: string; message: string; retryable: boolean } };

export async function fetchWeeklyReport(skuCode: string, weekId: number): Promise<WeeklyReport> {
  const response = await publicApiClient.get<WeeklyReport>(`/api/reports/${weekId}`, {
    params: { sku_code: skuCode },
  });
  return response.data;
}

function emitSseRecords(buffer: string, onEvent: (event: ReportStreamEvent) => void) {
  const records = buffer.split("\n\n");
  const remainder = records.pop() ?? "";
  for (const record of records) {
    const data = record.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
    if (data) {
      onEvent(JSON.parse(data) as ReportStreamEvent);
    }
  }
  return remainder;
}

export async function streamReportGeneration(
  payload: { sku_code: string; week_id: number },
  onEvent: (event: ReportStreamEvent) => void,
) {
  const token = getApiAccessToken();
  if (!token) {
    throw new Error("Authentication is required.");
  }
  const response = await fetch(`${apiClient.defaults.baseURL}/api/reports/generate`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
    throw new Error("The report could not be generated.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = emitSseRecords(buffer, onEvent);
    if (done) {
      break;
    }
  }
}
