"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { EmptyState, ErrorState, Skeleton } from "@/components/common";
import type { TransactionFilters } from "@/lib/api/client";
import { useAccounts, useBanks, useCategories, useTransactions } from "@/lib/api/hooks";
import type { PreviewState } from "@/lib/preview";
import type { Transaction } from "@/lib/types";

import { PAGE_SIZES, type ListPage, type PageSize } from "./filters";
import { TransactionCards, TransactionsTable, type ReferenceData } from "./transactions-table";

/** Category/account/bank names for joining with list rows (the list returns ids only — G-7). */
export function useReferenceData(): ReferenceData {
  const { data: categories } = useCategories();
  const { data: accounts } = useAccounts(true);
  const { data: banks } = useBanks();
  return useMemo(
    () => ({
      categories: new Map((categories ?? []).map((item) => [item.id, item])),
      accounts: new Map((accounts ?? []).map((item) => [item.id, item])),
      banks: new Map((banks ?? []).map((item) => [item.id, item])),
    }),
    [categories, accounts, banks],
  );
}

function LoadingRows() {
  return (
    <section
      className="transaction-table card-surface"
      aria-busy="true"
      aria-label="Загрузка операций"
    >
      <div className="table-scroll">
        {Array.from({ length: 8 }, (_, index) => (
          <div className="transaction-skeleton" key={index}>
            <Skeleton />
            <Skeleton />
            <Skeleton />
          </div>
        ))}
      </div>
    </section>
  );
}

export function Pagination({
  page,
  total,
  shown,
  note = "Сначала новые",
  onChange,
}: {
  page: ListPage;
  total: number;
  shown: number;
  /** Sort order hint shown on the left (the API has a single fixed order). */
  note?: string;
  onChange: (page: ListPage) => void;
}) {
  const from = total === 0 || shown === 0 ? 0 : page.offset + 1;
  const to = page.offset + shown;
  return (
    <div className="table-footer">
      <small>{note}</small>
      <div className="pagination">
        <span aria-live="polite">
          Показано {from}–{to} из {total}
        </span>
        <label>
          На странице
          <select
            value={page.limit}
            onChange={(event) =>
              onChange({ limit: Number(event.target.value) as PageSize, offset: 0 })
            }
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="pagination-buttons">
          <button
            type="button"
            aria-label="Предыдущая страница"
            className="button secondary small"
            disabled={page.offset === 0}
            onClick={() => onChange({ ...page, offset: Math.max(0, page.offset - page.limit) })}
          >
            <ChevronLeft aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Следующая страница"
            className="button secondary small"
            disabled={page.offset + page.limit >= total}
            onClick={() => onChange({ ...page, offset: page.offset + page.limit })}
          >
            <ChevronRight aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Data block of the transactions list: loading / error / empty / table + cards
 * and pagination. Calls `GET /transactions` with `filters` + `page`.
 */
export function TransactionsResults({
  filters,
  page,
  timeZone,
  hasUserFilters,
  preview = "default",
  emptyDescription = "Добавьте операцию вручную или импортируйте банковскую выписку.",
  onPageChange,
  onClearFilters,
  onAdd,
  onOpen,
}: {
  filters: Omit<TransactionFilters, "limit" | "offset">;
  page: ListPage;
  timeZone: string;
  hasUserFilters: boolean;
  preview?: PreviewState;
  emptyDescription?: string;
  onPageChange: (page: ListPage) => void;
  onClearFilters?: () => void;
  onAdd?: () => void;
  onOpen: (transaction: Transaction) => void;
}) {
  const query = useMemo(
    () => ({ ...filters, limit: page.limit, offset: page.offset }),
    [filters, page],
  );
  const { data, error, isLoading, mutate } = useTransactions(query);
  const reference = useReferenceData();

  if (preview === "error" || (error && !data)) {
    return (
      <section className="transaction-table card-surface">
        <ErrorState error={preview === "error" ? undefined : error} retry={() => void mutate()} />
      </section>
    );
  }
  if (preview === "loading" || (isLoading && !data) || !data) return <LoadingRows />;

  const items = preview === "empty" ? [] : data.items;
  if (items.length === 0) {
    if (page.offset > 0 && data.total > 0) {
      return (
        <section className="card-surface transaction-empty">
          <EmptyState
            title="На этой странице нет операций"
            description="Список изменился. Вернитесь к первой странице."
            action={
              <button
                type="button"
                className="button secondary"
                onClick={() => onPageChange({ ...page, offset: 0 })}
              >
                К первой странице
              </button>
            }
          />
        </section>
      );
    }
    return (
      <section className="card-surface transaction-empty">
        <EmptyState
          title={hasUserFilters ? "Ничего не найдено" : "Пока нет операций"}
          description={
            hasUserFilters ? "Измените условия поиска или сбросьте фильтры." : emptyDescription
          }
          action={
            hasUserFilters && onClearFilters ? (
              <button type="button" className="button secondary" onClick={onClearFilters}>
                Сбросить фильтры
              </button>
            ) : onAdd ? (
              <div className="empty-actions">
                <button type="button" className="button primary" onClick={onAdd}>
                  Добавить операцию
                </button>
                <Link className="button secondary" href="/transactions/import">
                  Импорт выписки
                </Link>
              </div>
            ) : undefined
          }
        />
      </section>
    );
  }

  return (
    <section className="transaction-table card-surface" aria-busy={isLoading || undefined}>
      {error && (
        <p className="form-error" role="alert">
          Не удалось обновить список. Показаны прежние данные.
        </p>
      )}
      <TransactionsTable items={items} reference={reference} onOpen={onOpen} />
      <TransactionCards items={items} reference={reference} timeZone={timeZone} onOpen={onOpen} />
      <Pagination page={page} total={data.total} shown={items.length} onChange={onPageChange} />
    </section>
  );
}
