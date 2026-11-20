import { Suspense } from "react";
import { notFound } from "next/navigation";
import { TransactionsScreen } from "@/components/transactions/transactions-screen";

export default async function TransactionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^\d{1,9}$/.test(id) || Number(id) <= 0) notFound();
  return (
    <Suspense fallback={<div className="state-row">Загрузка операции…</div>}>
      <TransactionsScreen initialId={Number(id)} />
    </Suspense>
  );
}
