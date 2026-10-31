import { describe, expect, it } from "vitest";
import { backendPython, browserConfiguration, liveConfiguration } from "../e2e/runtime.mjs";
import { askReceipt, reportReceipt } from "../e2e/receipt";

const runId = "11111111-1111-4111-8111-111111111111";
const env = { PHASE14_ALLOW_LIVE: "1", PHASE14_RUN_ID: runId,
  PHASE14_DATABASE_URL: "postgresql+asyncpg://test:test@127.0.0.1:55432/voc_phase14",
  PHASE14_MILVUS_COLLECTION: "aspect_mentions_phase14_1024" };
const turn = { session_id: runId, user_message_id: "22222222-2222-4222-8222-222222222222",
  assistant_message_id: "33333333-3333-4333-8333-333333333333" };
const done = `event: done\ndata: ${JSON.stringify({ event_type: "done", status: "success", ...turn })}\n\n`;

describe("acceptance runtime", () => {
  it("requires an explicit live opt-in and a dedicated data target", () => {
    expect(liveConfiguration(env).runId).toBe(runId);
    for (const patch of [ { PHASE14_ALLOW_LIVE: "0" }, { PHASE14_RUN_ID: "old" },
      { PHASE14_DATABASE_URL: "postgresql+asyncpg://secret@localhost/voc" },
      { PHASE14_DATABASE_URL: "postgresql+asyncpg://secret@remote/voc_phase14" },
      { PHASE14_DATABASE_URL: "postgresql+asyncpg://secret@localhost/voc_phase14?host=remote" },
      { PHASE14_MILVUS_COLLECTION: "aspect_mentions_vectors_1024" } ]) {
      expect(() => liveConfiguration({ ...env, ...patch })).toThrow();
    }
  });
  it("resolves Windows and Linux venvs without dereferencing interpreter symlinks", () => {
    expect(backendPython("C:\\My Repo", "win32", undefined, () => true))
      .toBe("C:\\My Repo\\.venv\\Scripts\\python.exe");
    expect(backendPython("/home/my repo", "linux", undefined, () => true))
      .toBe("/home/my repo/.venv/bin/python");
    expect(backendPython("/repo", "linux", "/custom/python", () => true)).toBe("/custom/python");
    expect(() => backendPython("/repo", "linux", "python", () => true)).toThrow();
    expect(() => backendPython("/repo", "linux", undefined, () => false)).toThrow();
  });
});

describe("SSE receipts", () => {
  it("keeps stable IDs while discarding answer text and other payload fields", () => {
    const stream = 'event: answer_delta\ndata: {"event_type":"answer_delta","delta":"private text"}\n\n';
    expect(askReceipt(stream + done)).toEqual(turn);
    expect(askReceipt(done.replace(/\n/g, "\r\n"))).toEqual(turn);
  });
  it.each(["", done + done, done.replace("event: done", "event: citation"),
    done.trimEnd(), 'data: {}\n\n' + done,
    done.replace(turn.user_message_id, "invalid"), done.replace('"success"', '"error"'),
    'event: error\ndata: {"event_type":"error","error":{}}\n\n' + done,
    done.replace(turn.user_message_id, turn.assistant_message_id),
  ])("rejects incomplete, failed and conflicting streams %#", (stream) => {
    expect(() => askReceipt(stream)).toThrow();
  });
});

describe("report receipts", () => {
  const report = { report_id: runId, sku_code: "ecoflow-delta2", week_id: 202403,
    generated_at: "2026-10-22T04:00:00.000Z", report_md: "private report", summary: "摘要" };
  const stream = `event: report_completed\ndata: ${JSON.stringify({ event_type: "report_completed", report })}\n\n`;
  it("requires completion of this request and discards report content", () => {
    expect(reportReceipt(stream)).toEqual({ report_id: runId, sku_code: "ecoflow-delta2",
      week_id: 202403, generated_at: report.generated_at,
      content_sha256: "4a223d027b1f83dd733f7e6d0e843260d9a15f16ca58aac3c6c402c7193a69bd" });
  });
  it.each(["", stream + stream, stream.replace(runId, "invalid"),
    stream.trimEnd(),
    stream.replace(report.generated_at, "yesterday"),
    'event: error\ndata: {"event_type":"error"}\n\n' + stream,
  ])("rejects failed or incomplete report streams %#", (body) => {
    expect(() => reportReceipt(body)).toThrow();
  });
});


describe("shared API browser configuration", () => {
  it("borrows only a loopback origin with an absolute receipt destination", () => {
    const shared = { ...env, PHASE14_API_BASE_URL: "http://127.0.0.1:43210",
      PHASE14_RECEIPT_DIR: process.cwd() };
    expect(browserConfiguration(shared)).toMatchObject({ external: true,
      apiBaseUrl: shared.PHASE14_API_BASE_URL });
    expect(browserConfiguration(env).external).toBe(false);
    for (const value of ["", "http://remote:1234", "http://127.0.0.1:0",
      "http://127.0.0.1:99999", "http://user:pass@127.0.0.1:1234",
      "http://127.0.0.1:1234/path", "http://127.0.0.1:1234?x=1"]) {
      expect(() => browserConfiguration({ ...shared, PHASE14_API_BASE_URL: value })).toThrow();
    }
    expect(() => browserConfiguration({ ...shared, PHASE14_RECEIPT_DIR: "relative" })).toThrow();
    expect(() => browserConfiguration({ ...shared, PHASE14_ALLOW_LIVE: "0" })).toThrow();
  });
});
