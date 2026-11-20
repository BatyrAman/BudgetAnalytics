"use client";

import { useState } from "react";
import { Plus } from "lucide-react";

import { currentTimezone, type TransactionFilters } from "@/lib/api/client";

import { DEFAULT_PAGE_SIZE, type ListPage, type PageSize } from "./filters";
import { useTransactionOverlays } from "./transaction-overlays";
import { TransactionsResults } from "./transactions-results";

/**
 * Fixed filters an embedding screen can apply. `start_date` / `end_date` must be
 * ISO date-times with an offset (inclusive); build them with `localDayStart` /
 * `localDayEnd` from `components/transactions/period.ts` to get local day bounds.
 */
export type FixedTransactionFilters = Pick<
  TransactionFilters,
  | "account_id"
  | "category_id"
  | "bank_id"
  | "transaction_type"
  | "currency"
  | "start_date"
  | "end_date"
>;

export type TransactionsListProps = {
  /**
   * Filters sent with every `GET /transactions` request; the user cannot change
   * them. Examples: `{ account_id: 5 }` (account details) or
   * `{ category_id: 3, transaction_type: "expense", start_date, end_date }` (budget month).
   */
  filters: FixedTransactionFilters;
  /** Rows per page (20, 50 or 100). Default 20; the user can change it in the footer. */
  pageSize?: PageSize;
  /**
   * Show «Добавить операцию». The form is prefilled with `account_id`, `category_id`
   * and `transaction_type` from `filters`. Default `true`.
   */
  allowCreate?: boolean;
  /** Text of the empty state when there are no transactions for `filters`. */
  emptyDescription?: string;
};

/**
 * Embeddable, paginated transactions list (newest first) with the details drawer
 * and the create/edit dialog. Reads `GET /transactions`; does not touch the URL.
 *
 * ```tsx
 * <TransactionsList filters={{ account_id: account.id }} />
 * ```
 */
export function TransactionsList({
  filters,
  pageSize = DEFAULT_PAGE_SIZE,
  allowCreate = true,
  emptyDescription = "Здесь пока нет операций.",
}: TransactionsListProps) {
  const [timeZone] = useState(currentTimezone);
  const [page, setPage] = useState<ListPage>({ limit: pageSize, offset: 0 });
  // Back to the first page when the embedding screen changes the fixed filters.
  const filtersKey = JSON.stringify(filters);
  const [seenKey, setSeenKey] = useState(filtersKey);
  if (seenKey !== filtersKey) {
    setSeenKey(filtersKey);
    setPage((current) => ({ ...current, offset: 0 }));
  }
  const overlays = useTransactionOverlays({
    defaults: {
      account_id: filters.account_id,
      category_id: filters.category_id,
      transaction_type: filters.transaction_type,
    },
  });

  return (
    <div className="embedded-transactions-page">
      {allowCreate && (
        <div className="filter-actions">
          <button type="button" className="button secondary small" onClick={overlays.openCreate}>
            <Plus aria-hidden="true" />
            Добавить операцию
          </button>
        </div>
      )}
      <TransactionsResults
        filters={filters}
        page={page}
        timeZone={timeZone}
        hasUserFilters={false}
        emptyDescription={emptyDescription}
        onPageChange={setPage}
        onOpen={(transaction) => overlays.openDetails(transaction.id)}
      />
      {overlays.element}
    </div>
  );
}
