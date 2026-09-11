import { FeaturePlaceholder } from "@/components/feature-placeholder";

export default async function SkuDetailPage(props: {
  params: Promise<{ sku_code: string }>;
}) {
  const { sku_code: skuCode } = await props.params;
  return <FeaturePlaceholder eyebrow="SKU monitoring" title="SKU detail" description={`The shared detail workspace is ready for ${skuCode}. Metrics, trends, and evidence will be added in the dedicated SKU phase.`} dataSource={"GET /api/skus/{sku_code}?week_id=YYYYWW\nGET /api/skus/{sku_code}/trends?weeks=1..12\nGET /api/skus/{sku_code}/evidence?..."} />;
}
