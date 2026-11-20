import { Suspense } from "react";
import { ImportWizard } from "@/components/transactions/import-wizard";

export default function ImportPage() {
  return (
    <Suspense fallback={<div className="state-row">Загрузка импорта…</div>}>
      <ImportWizard />
    </Suspense>
  );
}
