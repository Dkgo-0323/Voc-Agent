import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AskWorkspace } from "@/components/ask/ask-workspace";

const askApi = vi.hoisted(() => ({ streamAsk: vi.fn() }));
vi.mock("@/lib/api/ask", () => askApi);

const citation = { mention_id: "00000000-0000-0000-0000-000000000101", document_id: "00000000-0000-0000-0000-000000000201", evidence_preview: "It lasted through the whole weekend.", sku_code: "ecoflow-delta2", aspect_label: "battery_capacity", sentiment: "positive" as const, week_id: 202403, source: { document_id: "00000000-0000-0000-0000-000000000201", sku_code: "ecoflow-delta2", platform: "amazon", published_at: null, source_url: "https://example.test/review/201", title: "Weekend power", rating: null, review_text: null } };

function ask(question: string) {
  fireEvent.change(screen.getByLabelText("Ask a question"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("AskWorkspace", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    askApi.streamAsk.mockReset();
    let requestNumber = 0;
    vi.stubGlobal("crypto", { randomUUID: () => `request-${++requestNumber}` });
  });

  it("renders a quantitative answer with friendly tool progress and stable completion", async () => {
    askApi.streamAsk.mockImplementation(async (_message: string, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "tool_started", call_id: "sql-1", tool_name: "tool_sql" });
      onEvent({ event_type: "answer_delta", delta: "There were 12 reviews." });
      onEvent({ event_type: "done", session_id: "session-1", status: "success" });
    });
    render(<AskWorkspace />);
    ask("How many reviews?");

    expect(await screen.findByText("There were 12 reviews.")).toBeInTheDocument();
    expect(askApi.streamAsk).toHaveBeenCalledWith("How many reviews?", expect.any(Function), expect.objectContaining({ sessionId: undefined }));
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("renders only used RAG citations in an accessible popover", async () => {
    askApi.streamAsk.mockImplementation(async (_message: string, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "tool_started", call_id: "sql-1", tool_name: "tool_sql" });
      onEvent({ event_type: "tool_started", call_id: "rag-1", tool_name: "tool_rag" });
      onEvent({ event_type: "answer_delta", delta: "Customers praised weekend runtime." });
      onEvent({ event_type: "citation", citation });
      onEvent({ event_type: "done", session_id: "session-1", status: "success" });
    });
    render(<AskWorkspace />);
    ask("What do customers praise?");
    await screen.findByText("Customers praised weekend runtime.");

    fireEvent.click(screen.getByRole("button", { name: "Open citation 1" }));
    expect(screen.getByRole("dialog", { name: "Citation 1" })).toHaveTextContent("It lasted through the whole weekend.");
    expect(screen.getByRole("dialog", { name: "Citation 1" })).toHaveTextContent("amazon · ecoflow-delta2 · Week 202403");
  });

  it("passes the completed session to a visible follow-up and handles abstention", async () => {
    askApi.streamAsk.mockImplementation(async (_message: string, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "answer_delta", delta: "Initial answer." });
      onEvent({ event_type: "done", session_id: "session-1", status: "success" });
    });
    render(<AskWorkspace />);
    ask("First question");
    await screen.findByText("Initial answer.");

    askApi.streamAsk.mockImplementation(async (_message: string, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "answer_delta", delta: "I do not have matching data." });
      onEvent({ event_type: "done", session_id: "session-1", status: "abstained" });
    });
    ask("What about next week?");
    expect(await screen.findAllByText("No matching VOC data was found for this request.")).toHaveLength(1);
    expect(askApi.streamAsk).toHaveBeenLastCalledWith("What about next week?", expect.any(Function), expect.objectContaining({ sessionId: "session-1" }));
  });

  it("surfaces a safe invalid-comparison error and supports cancellation", async () => {
    askApi.streamAsk.mockImplementation(async (_message: string, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "error", error: { code: "capacity_tier_mismatch", message: "Direct SKU comparison requires the same capacity tier.", retryable: false } });
    });
    render(<AskWorkspace />);
    ask("Compare incompatible SKUs");
    expect(await screen.findByText("Direct SKU comparison requires the same capacity tier.")).toBeInTheDocument();

    askApi.streamAsk.mockImplementation((_message: string, _onEvent: unknown, options: { signal: AbortSignal }) => new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))));
    ask("Cancel this request");
    fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
    expect(await screen.findByText("Request cancelled before an answer was completed.")).toBeInTheDocument();
  });

  it("shows a safe authentication failure without exposing transport details", async () => {
    askApi.streamAsk.mockRejectedValue(new Error("Authentication is required."));
    render(<AskWorkspace />);
    ask("Can I ask a question?");

    expect(await screen.findByText("Authentication is required.")).toBeInTheDocument();
  });

  it("shows a retryable safe error when the answer stream ends without a terminal event", async () => {
    askApi.streamAsk.mockResolvedValue(undefined);
    render(<AskWorkspace />);
    ask("What happened to the stream?");

    expect(await screen.findByText("The response stream ended before an answer was completed. Please try again.")).toBeInTheDocument();
  });

  it("does not treat an error completion status as a successful answer", async () => {
    askApi.streamAsk.mockImplementation(async (_message: string, onEvent: (event: unknown) => void) => {
      onEvent({ event_type: "done", session_id: "session-1", status: "error" });
    });
    render(<AskWorkspace />);
    ask("Can this complete with an error?");

    expect(await screen.findByText("The response could not be completed. Please try again.")).toBeInTheDocument();
  });
});
