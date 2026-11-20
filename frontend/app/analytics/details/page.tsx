import { Suspense } from "react";
import { AnalyticsDetailsScreen } from "@/components/analytics/analytics-screens";

export default function AnalyticsDetailsPage() {
  return (
    <Suspense fallback={<div className="state-row">Загрузка аналитики…</div>}>
      <AnalyticsDetailsScreen />
    </Suspense>
  );
}
