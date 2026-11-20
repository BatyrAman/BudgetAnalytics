import { Suspense } from "react";
import { TransactionsScreen } from "@/components/transactions/transactions-screen";

export default function TransactionsPage() {
  return (
    <Suspense fallback={<div className="state-row">Загрузка операций…</div>}>
      <TransactionsScreen />
    </Suspense>
  );
}
