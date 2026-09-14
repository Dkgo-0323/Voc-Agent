"use client";

import { Bot, CircleStop, Send, Sparkles, UserRound } from "lucide-react";
import { useRef, useState } from "react";
import { PageHeader, PageLayout, Surface } from "@/components/ui/page-layout";
import { toApiError } from "@/lib/api/client";
import type { EvidenceCitation } from "@/lib/api/dashboard";
import { streamAsk, type AskStreamEvent } from "@/lib/api/ask";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: EvidenceCitation[];
  status?: "working" | "complete" | "abstained" | "error" | "cancelled";
  progress?: string;
  error?: string;
};

const toolLabels: Record<string, string> = {
  tool_sql: "Calculating structured VOC metrics…",
  tool_rag: "Searching relevant customer evidence…",
  tool_report: "Checking available weekly report context…",
};

function MarkdownAnswer({ content }: { content: string }) {
  return (
    <div className="space-y-3 whitespace-pre-wrap text-sm leading-6">
      {content
        .split("\n\n")
        .filter(Boolean)
        .map((block, index) => {
          if (block.startsWith("## ")) {
            return <h3 key={index} className="text-base font-semibold">{block.slice(3)}</h3>;
          }
          const lines = block.split("\n");
          if (lines.every((line) => line.startsWith("- "))) {
            return <ul key={index} className="list-disc space-y-1 pl-5">{lines.map((line) => <li key={line}>{line.slice(2)}</li>)}</ul>;
          }
          return <p key={index}>{block}</p>;
        })}
    </div>
  );
}

function CitationPopover({ citation, number }: { citation: EvidenceCitation; number: number }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button type="button" aria-label={`Open citation ${number}`} aria-expanded={open} onClick={() => setOpen((current) => !current)} className="ml-1 rounded px-1.5 py-0.5 text-xs font-bold text-[var(--brand-strong)] hover:bg-[var(--brand-soft)]">[{number}]</button>
      {open ? <div role="dialog" aria-label={`Citation ${number}`} className="absolute bottom-full right-0 z-10 mb-2 w-[min(20rem,calc(100vw-2.5rem))] rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 text-left shadow-lg"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--brand)]">Citation {number}</p><blockquote className="mt-2 break-words text-sm leading-6 text-[var(--ink)]">“{citation.evidence_preview}”</blockquote><p className="mt-3 break-words text-xs text-[var(--ink-muted)]">{citation.source.platform} · {citation.sku_code} · Week {citation.week_id}</p>{citation.source.title ? <p className="mt-2 break-words text-xs text-[var(--ink-muted)]">{citation.source.title}</p> : null}{citation.source.source_url ? <a href={citation.source.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-block break-all text-xs font-semibold text-[var(--brand-strong)]">Open original source</a> : null}</div> : null}
    </span>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  return (
    <article className="flex gap-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--brand-soft)] text-[var(--brand)]"><Bot size={16} /></span>
      <div className="min-w-0 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3 shadow-[var(--shadow)]">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--brand)]">VOC Agent</p>
        {message.status === "working" ? <p role="status" className="mt-2 text-sm text-[var(--ink-muted)]">{message.progress ?? "Working on your request…"}</p> : null}
        {message.status === "abstained" ? <p className="mt-2 text-sm font-medium text-[var(--ink-muted)]">No matching VOC data was found for this request.</p> : null}
        {message.status === "cancelled" ? <p className="mt-2 text-sm text-[var(--ink-muted)]">Request cancelled before an answer was completed.</p> : null}
        {message.error ? <p role="alert" className="mt-2 text-sm font-medium text-[var(--danger)]">{message.error}</p> : null}
        {message.content ? <div className="mt-3"><MarkdownAnswer content={message.content} /></div> : null}
        {message.citations.length ? <div className="mt-4 border-t border-[var(--line)] pt-3"><p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--ink-muted)]">Used sources</p><div className="mt-2 flex flex-wrap gap-1">{message.citations.map((citation, index) => <CitationPopover key={citation.mention_id} citation={citation} number={index + 1} />)}</div></div> : null}
      </div>
    </article>
  );
}

export function AskWorkspace() {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [isRunning, setIsRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const updateAssistant = (id: string, update: (message: ChatMessage) => ChatMessage) => setMessages((current) => current.map((message) => message.id === id ? update(message) : message));

  const submit = async () => {
    const content = draft.trim();
    if (!content || isRunning) return;
    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsRunning(true);
    setDraft("");
    setMessages((current) => [...current, { id: `${requestId}:user`, role: "user", content, citations: [] }, { id: requestId, role: "assistant", content: "", citations: [], status: "working", progress: "Preparing your request…" }]);
    let streamError = "";
    let terminalEventReceived = false;
    try {
      await streamAsk(content, (event: AskStreamEvent) => {
        if (event.event_type === "tool_started") updateAssistant(requestId, (message) => ({ ...message, progress: toolLabels[event.tool_name] ?? "Preparing a grounded response…" }));
        if (event.event_type === "tool_completed" && event.status === "error") updateAssistant(requestId, (message) => ({ ...message, progress: "Continuing with available VOC data…" }));
        if (event.event_type === "answer_delta") updateAssistant(requestId, (message) => ({ ...message, content: message.content + event.delta, progress: "Preparing the final response…" }));
        if (event.event_type === "citation") updateAssistant(requestId, (message) => ({ ...message, citations: message.citations.some((citation) => citation.mention_id === event.citation.mention_id) ? message.citations : [...message.citations, event.citation] }));
        if (event.event_type === "done") {
          terminalEventReceived = true;
          if (event.session_id) setSessionId(event.session_id);
          if (event.status === "error") streamError = "The response could not be completed. Please try again.";
          else updateAssistant(requestId, (message) => ({ ...message, status: event.status === "abstained" ? "abstained" : "complete", progress: undefined }));
        }
        if (event.event_type === "error") {
          terminalEventReceived = true;
          streamError = event.error.message;
        }
      }, { sessionId, signal: controller.signal });
      if (streamError || !terminalEventReceived) updateAssistant(requestId, (message) => ({ ...message, status: "error", error: streamError || "The response stream ended before an answer was completed. Please try again.", progress: undefined }));
    } catch (caught) {
      if (controller.signal.aborted) updateAssistant(requestId, (message) => ({ ...message, status: "cancelled", progress: undefined }));
      else updateAssistant(requestId, (message) => ({ ...message, status: "error", error: toApiError(caught).message, progress: undefined }));
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      setIsRunning(false);
    }
  };

  const cancel = () => controllerRef.current?.abort();
  const startNewConversation = () => { controllerRef.current?.abort(); controllerRef.current = null; setIsRunning(false); setSessionId(undefined); setMessages([]); setDraft(""); };

  return <PageLayout><PageHeader eyebrow="Controlled Agent" title="Ask your data" description="Ask for a metric, trend, evidence, or grounded comparison. The Agent uses only approved analytics and retrieval tools." actions={<button type="button" onClick={startNewConversation} className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold">New conversation</button>} /><div className="mt-7 grid gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]"><Surface className="min-h-[34rem]"><div className="space-y-5">{messages.length ? messages.map((message) => message.role === "user" ? <article key={message.id} className="flex justify-end gap-3"><div className="max-w-[80%] rounded-xl bg-[var(--brand)] px-4 py-3 text-sm leading-6 text-white">{message.content}</div><span className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--ink)] text-white"><UserRound size={16} /></span></article> : <AssistantMessage key={message.id} message={message} />) : <div className="flex min-h-72 flex-col items-center justify-center text-center"><Sparkles className="text-[var(--brand)]" size={28} /><h2 className="mt-4 text-lg font-semibold">Ask a grounded VOC question</h2><p className="mt-2 max-w-md text-sm leading-6 text-[var(--ink-muted)]">Try a review count, a complaint theme, or a same-tier competitor comparison.</p></div>}</div><form onSubmit={(event) => { event.preventDefault(); void submit(); }} className="mt-6 border-t border-[var(--line)] pt-5"><label className="sr-only" htmlFor="ask-message">Ask a question</label><textarea id="ask-message" value={draft} onChange={(event) => setDraft(event.target.value)} disabled={isRunning} placeholder="For example: What are the main complaints about EcoFlow DELTA 2?" className="min-h-24 w-full resize-y rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-3 text-sm leading-6 outline-none focus:border-[var(--brand)] disabled:opacity-70" /><div className="mt-3 flex items-center justify-between gap-3"><p className="text-xs text-[var(--ink-muted)]">Follow-ups continue only this visible conversation.</p>{isRunning ? <button type="button" onClick={cancel} className="inline-flex items-center gap-2 rounded-lg border border-[var(--line)] px-4 py-2 text-sm font-semibold"><CircleStop size={16} />Stop</button> : <button type="submit" disabled={!draft.trim()} className="inline-flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"><Send size={16} />Send</button>}</div></form></Surface><Surface><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--brand)]">How answers stay grounded</p><ul className="mt-4 space-y-3 text-sm leading-6 text-[var(--ink-muted)]"><li>Metrics are calculated by deterministic backend services.</li><li>Customer examples appear only when the Agent emits a used citation.</li><li>Follow-ups use the saved recent-message conversation, not hidden filters.</li><li>No matching data is shown as an abstention rather than a guessed answer.</li></ul></Surface></div></PageLayout>;
}
