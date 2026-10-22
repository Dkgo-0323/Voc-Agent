import { createHash } from "node:crypto";

export type AskReceipt = {
  session_id: string;
  user_message_id: string;
  assistant_message_id: string;
};

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Consume the completed HTTP body. Never save response text, JWTs or headers.
export function askReceipt(body: string): AskReceipt {
  if (!body.replace(/\r\n/g, "\n").endsWith("\n\n")) throw new Error("Ask SSE frame was truncated.");
  let done: AskReceipt | undefined;
  let terminal = false;
  for (const block of body.replace(/\r\n/g, "\n").split("\n\n")) {
    const lines = block.split("\n");
    const name = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    const data = lines.filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart()).join("\n");
    if (!data) continue;
    if (terminal) throw new Error("Ask emitted data after its terminal event.");
    const value = JSON.parse(data) as Record<string, unknown>;
    if (!name || !["tool_started", "tool_completed", "answer_delta", "citation", "done", "error"].includes(name)
        || name !== value.event_type) throw new Error("Ask SSE event type mismatch.");
    if (name === "error") throw new Error("Ask returned a terminal error.");
    if (name === "done") {
      if (!["success", "partial", "abstained"].includes(String(value.status))) {
        throw new Error("Ask did not complete successfully.");
      }
      const receipt = {} as AskReceipt;
      for (const key of ["session_id", "user_message_id", "assistant_message_id"] as const) {
        if (typeof value[key] !== "string" || !uuid.test(value[key])) {
          throw new Error("Ask done event is missing a stable UUID.");
        }
        receipt[key] = value[key].toLowerCase();
      }
      if (receipt.user_message_id === receipt.assistant_message_id) {
        throw new Error("Ask reused a message UUID.");
      }
      done = receipt;
      terminal = true;
    }
  }
  if (!done) throw new Error("Ask stream ended without done.");
  return done;
}

export type ReportReceipt = { report_id: string; sku_code: string; week_id: number;
  generated_at: string; content_sha256: string };

export function reportReceipt(body: string): ReportReceipt {
  if (!body.replace(/\r\n/g, "\n").endsWith("\n\n")) throw new Error("Report SSE frame was truncated.");
  let receipt: ReportReceipt | undefined;
  for (const block of body.replace(/\r\n/g, "\n").split("\n\n")) {
    const lines = block.split("\n");
    const name = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    const data = lines.filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart()).join("\n");
    if (!data) continue;
    if (receipt) throw new Error("Report emitted data after completion.");
    const value = JSON.parse(data) as Record<string, unknown>;
    if (!name || !["report_started", "stage_started", "stage_completed", "report_delta", "report_completed", "error"].includes(name)
        || name !== value.event_type) throw new Error("Report SSE event type mismatch.");
    if (name === "error") throw new Error("Report returned a terminal error.");
    if (name === "report_completed") {
      const report = value.report as (ReportReceipt & { report_md: string; summary: string }) | undefined;
      if (!report || typeof report.report_id !== "string" || !uuid.test(report.report_id)
          || typeof report.sku_code !== "string" || !report.sku_code
          || !Number.isInteger(report.week_id) || typeof report.generated_at !== "string"
          || !Number.isFinite(Date.parse(report.generated_at))
          || typeof report.report_md !== "string" || typeof report.summary !== "string") {
        throw new Error("Report completed without valid persisted metadata.");
      }
      receipt = { report_id: report.report_id.toLowerCase(), sku_code: report.sku_code,
        week_id: report.week_id, generated_at: report.generated_at,
        content_sha256: createHash("sha256").update(JSON.stringify([report.report_md, report.summary])).digest("hex") };
    }
  }
  if (!receipt) throw new Error("Report stream ended without report_completed.");
  return receipt;
}
