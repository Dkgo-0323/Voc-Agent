import { FeaturePlaceholder } from "@/components/feature-placeholder";

export default function AskPage() {
  return <FeaturePlaceholder eyebrow="Controlled Agent" title="Ask your data" description="The streaming conversation workspace will render only safe tool progress, final answer Markdown, and citations actually used." dataSource="POST /api/ask (authenticated SSE)" />;
}
