import { FeaturePlaceholder } from "@/components/feature-placeholder";

export default function ComparePage() {
  return <FeaturePlaceholder eyebrow="Controlled comparison" title="Compare SKUs" description="The comparison workspace will only offer same-capacity-tier products and will preserve server-side validation." dataSource="GET /api/compare?sku_code={code}&sku_code={code}&week_id=YYYYWW" />;
}
