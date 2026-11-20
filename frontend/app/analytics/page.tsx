import { Suspense } from "react";
import { AnalyticsOverviewScreen } from "@/components/analytics/analytics-screens";

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<div className="state-row">Загрузка аналитики…</div>}>
      <AnalyticsOverviewScreen />
    </Suspense>
  );
}
