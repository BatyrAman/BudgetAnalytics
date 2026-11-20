"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { History, Plus, Upload } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/common";
import { currentTimezone } from "@/lib/api/client";
import { useAccounts, useBanks, useCategories } from "@/lib/api/hooks";
import { usePreviewState } from "@/lib/preview";

import {
  buildListQuery,
  countActiveFilters,
  isAmountRangeInvalid,
  parseListQuery,
  type ListFilters,
  type ListPage,
} from "./filters";
import { useTransactionOverlays } from "./transaction-overlays";
import { TransactionsFilters } from "./transactions-filters";
import { TransactionsList, type FixedTransactionFilters } from "./transactions-list";
import { TransactionsResults } from "./transactions-results";

const BASE_PATH = "/transactions";

function withoutUndefined(filters: ListFilters): ListFilters {
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== ""),
  ) as ListFilters;
}

/** Filters actually sent to the API: inconsistent ranges are not sent (validated on the client). */
function requestFilters(filters: ListFilters) {
  const result = { ...filters };
  const problems: string[] = [];
  if (isAmountRangeInvalid(filters.min_amount, filters.max_amount)) {
    delete result.min_amount;
    delete result.max_amount;
    problems.push(
      "Минимальная сумма не может быть больше максимальной — фильтр по сумме не применён.",
    );
  }
  if (
    filters.start_date &&
    filters.end_date &&
    new Date(filters.start_date).getTime() > new Date(filters.end_date).getTime()
  ) {
    delete result.start_date;
    delete result.end_date;
    problems.push("Дата окончания должна быть не раньше даты начала — период не применён.");
  }
  return { filters: result, problems };
}

/**
 * T-1 transactions page. Filters and pagination live in the URL query
 * (`?category_id=3&start_date=…&limit=50&offset=50`); `?new=1` opens the create
 * dialog and `/transactions/[id]` opens the details drawer (`initialId`).
 */
function TransactionsPage({ initialId }: { initialId?: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preview = usePreviewState();
  const [timeZone] = useState(currentTimezone);
  const [now] = useState(() => new Date());
  const queryString = searchParams.toString();
  const { filters, page } = useMemo(
    () => parseListQuery(new URLSearchParams(queryString), timeZone),
    [queryString, timeZone],
  );

  const { data: categories } = useCategories();
  const { data: accounts } = useAccounts(true);
  const { data: banks } = useBanks();
  const options = useMemo(
    () => ({ categories: categories ?? [], accounts: accounts ?? [], banks: banks ?? [] }),
    [categories, accounts, banks],
  );

  const navigate = (nextFilters: ListFilters, nextPage: ListPage) => {
    const query = buildListQuery(nextFilters, nextPage);
    router.replace(query ? `${BASE_PATH}?${query}` : BASE_PATH, { scroll: false });
  };
  const listUrl = () => {
    const query = buildListQuery(filters, page);
    return query ? `${BASE_PATH}?${query}` : BASE_PATH;
  };

  const wantsNew = searchParams.get("new") === "1";
  const overlays = useTransactionOverlays({
    initialDetailsId: initialId ?? null,
    initialFormOpen: wantsNew,
    onDetailsClosed: () => {
      if (initialId !== undefined) router.replace(listUrl(), { scroll: false });
    },
    onFormClosed: () => {
      if (searchParams.get("new") === "1") router.replace(listUrl(), { scroll: false });
    },
  });
  // `?new=1` can also arrive while the page is open (e.g. the shell's «+» button).
  const [seenWantsNew, setSeenWantsNew] = useState(wantsNew);
  if (wantsNew !== seenWantsNew) {
    setSeenWantsNew(wantsNew);
    if (wantsNew) overlays.openCreate();
  }

  const activeCount = countActiveFilters(filters);
  const sent = requestFilters(filters);

  return (
    <div className="transactions-page">
      <PageHeader
        title="Операции"
        description="История доходов, расходов и переводов"
        actions={
          <>
            <Link className="button ghost" href="/transactions/import/history">
              <History aria-hidden="true" />
              История импортов
            </Link>
            <Link className="button secondary" href="/transactions/import">
              <Upload aria-hidden="true" />
              Импорт выписки
            </Link>
            <button type="button" className="button primary" onClick={overlays.openCreate}>
              <Plus aria-hidden="true" />
              Добавить операцию
            </button>
          </>
        }
      />
      <TransactionsFilters
        filters={filters}
        options={options}
        timeZone={timeZone}
        now={now}
        activeCount={activeCount}
        onChange={(patch) =>
          navigate(withoutUndefined({ ...filters, ...patch }), { limit: page.limit, offset: 0 })
        }
        onReset={() => navigate({}, { limit: page.limit, offset: 0 })}
      />
      {sent.problems.map((problem) => (
        <p className="form-error" role="alert" key={problem}>
          {problem}
        </p>
      ))}
      <TransactionsResults
        filters={sent.filters}
        page={page}
        timeZone={timeZone}
        hasUserFilters={activeCount > 0}
        preview={preview}
        onPageChange={(nextPage) => navigate(filters, nextPage)}
        onClearFilters={() => navigate({}, { limit: page.limit, offset: 0 })}
        onAdd={overlays.openCreate}
        onOpen={(transaction) => overlays.openDetails(transaction.id)}
      />
      {overlays.element}
    </div>
  );
}

/**
 * Transactions screen.
 *
 * Full page: `<TransactionsScreen />` (or `initialId` for `/transactions/[id]`).
 * The `embedded` / `fixedAccountId` / `fixedFilters` props are kept for existing
 * callers and render {@link TransactionsList}; new code should use
 * `TransactionsList` from `./transactions-list` directly.
 */
export function TransactionsScreen({
  initialId,
  embedded = false,
  fixedAccountId,
  fixedFilters,
}: {
  initialId?: number;
  embedded?: boolean;
  /** @deprecated use `<TransactionsList filters={{ account_id }} />` */
  fixedAccountId?: number;
  /** @deprecated use `<TransactionsList filters={…} />` */
  fixedFilters?: FixedTransactionFilters;
}) {
  if (embedded) {
    const filters: FixedTransactionFilters = {
      ...(fixedAccountId ? { account_id: fixedAccountId } : {}),
      ...fixedFilters,
    };
    return <TransactionsList filters={filters} />;
  }
  return (
    <AppShell>
      <TransactionsPage initialId={initialId} />
    </AppShell>
  );
}
