import { Suspense } from "react";
import { DepositsListScreen } from "@/components/deposits/deposit-screens";

export default function DepositsPage() {
  return (
    <Suspense fallback={<div className="state-row">Загрузка депозитов…</div>}>
      <DepositsListScreen />
    </Suspense>
  );
}
