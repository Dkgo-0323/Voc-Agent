import { AUTH_UNAUTHORIZED_EVENT, apiClient, getApiAccessToken } from "@/lib/api/client";
import type { EvidenceCitation } from "@/lib/api/dashboard";

export type AskStreamEvent =
  | { event_type: "tool_started"; tool_name: string }
  | { event_type: "tool_completed"; tool_name: string; status: string }
  | { event_type: "answer_delta"; delta: string }
  | { event_type: "citation"; citation: EvidenceCitation }
  | { event_type: "done"; status: string | null }
  | { event_type: "error"; error: { code: string; message: string; retryable: boolean } };

function emitSseRecords(buffer: string, onEvent: (event: AskStreamEvent) => void) {
  const records = buffer.split("\n\n");
  const remainder = records.pop() ?? "";
  for (const record of records) {
    const data = record.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
    if (data) {
      onEvent(JSON.parse(data) as AskStreamEvent);
    }
  }
  return remainder;
}

export async function streamAsk(
  message: string,
  onEvent: (event: AskStreamEvent) => void,
) {
  const token = getApiAccessToken();
  if (!token) {
    throw new Error("Authentication is required.");
  }
  const response = await fetch(`${apiClient.defaults.baseURL}/api/ask`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message }),
  });
  if (!response.ok || !response.body) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
    throw new Error("The comparison summary could not be generated.");
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
