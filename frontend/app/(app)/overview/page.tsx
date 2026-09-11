import { FeaturePlaceholder } from "@/components/feature-placeholder";

export default function OverviewPage() {
  return <FeaturePlaceholder eyebrow="Portfolio monitoring" title="Overview" description="A single place to monitor the covered week, portfolio sentiment, and SKU signals." dataSource={"GET /api/weeks\nGET /api/overview?week_id=YYYYWW"} />;
}
