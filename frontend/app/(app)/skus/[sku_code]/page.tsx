import { SkuDetailDashboard } from "@/components/sku/sku-detail-dashboard";

export default async function SkuDetailPage(props: {
  params: Promise<{ sku_code: string }>;
}) {
  const { sku_code: skuCode } = await props.params;
  return <SkuDetailDashboard skuCode={skuCode} />;
}
