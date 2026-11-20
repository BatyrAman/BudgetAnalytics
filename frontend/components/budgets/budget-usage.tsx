import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react";

import { formatMoney, formatPercent } from "@/lib/format";
import type { BudgetUtilization } from "@/lib/types";

export type UsageTone = "is-normal" | "is-warning" | "is-over";

/** D-7: warning from 80 %; «exceeded» only by the API flag. Number() is for colouring only. */
export function usageTone(usage: BudgetUtilization): UsageTone {
  if (usage.is_exceeded) return "is-over";
  return Number(usage.utilization_percent) >= 80 ? "is-warning" : "is-normal";
}

/** Status text; the overspend amount is the API `remaining` (negative) shown without sign. */
export function usageStatus(usage: BudgetUtilization): string {
  if (usage.is_exceeded) {
    return `Превышен на ${formatMoney(usage.remaining, usage.currency_code, { sign: null })}`;
  }
  return usageTone(usage) === "is-warning" ? "Близко к лимиту" : "В пределах лимита";
}

export function UsageStatusBadge({ usage }: { usage: BudgetUtilization }) {
  const tone = usageTone(usage);
  const Icon =
    tone === "is-over" ? CircleAlert : tone === "is-warning" ? TriangleAlert : CircleCheck;
  return (
    <span className={`budget-status-badge ${tone}`} data-tone={tone}>
      <Icon size={12} aria-hidden="true" /> {usageStatus(usage)}
    </span>
  );
}

/** Progress bar: width capped at 100 % visually, the label shows the real percent. */
export function UsageBar({ usage, label }: { usage: BudgetUtilization; label: string }) {
  const tone = usageTone(usage);
  const percent = Number(usage.utilization_percent);
  const width = Number.isFinite(percent) ? Math.max(0, Math.min(percent, 100)) : 0;
  return (
    <div
      className="budget-progress-track"
      role="progressbar"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={formatPercent(usage.utilization_percent, true)}
    >
      <span
        className={`budget-progress-fill ${tone}`}
        data-testid="budget-progress-fill"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
