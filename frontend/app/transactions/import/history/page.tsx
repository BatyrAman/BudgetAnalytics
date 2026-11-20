import { Suspense } from "react";
import { ImportHistory } from "@/components/transactions/import-history";

export default function ImportHistoryPage() {
  return (
    <Suspense fallback={<div className="state-row">Загрузка истории импортов…</div>}>
      <ImportHistory />
    </Suspense>
  );
}
