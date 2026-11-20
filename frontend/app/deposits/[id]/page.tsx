import { DepositDetailScreen } from "@/components/deposits/deposit-screens";

export default async function DepositPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DepositDetailScreen id={Number(id)} />;
}
