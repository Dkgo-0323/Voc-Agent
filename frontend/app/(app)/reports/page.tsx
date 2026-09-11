import { FeaturePlaceholder } from "@/components/feature-placeholder";

export default function ReportsPage() {
  return <FeaturePlaceholder eyebrow="Weekly intelligence" title="Reports" description="Stored report viewing and safe streamed generation will be added without exposing an incomplete candidate as persisted." dataSource={"GET /api/reports/{week_id}?sku_code={code}\nPOST /api/reports/generate (SSE)"} />;
}
