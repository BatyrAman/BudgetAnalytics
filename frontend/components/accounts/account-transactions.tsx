"use client";

import Link from "next/link";
import { useState } from "react";
import { EmptyState, ErrorState, Skeleton } from "@/components/common";
import { useCategories, useTransactions } from "@/lib/api/hooks";
import { formatDate, formatMoney, signForType } from "@/lib/format";

const PAGE_SIZE = 10;

/**
 * Compact operations list of one account (`GET /transactions?account_id=`).
 * The full Operations screen is not embeddable without navigating away, so this
 * screen renders its own read-only list and links to /transactions for editing.
 */
export function AccountTransactions({ accountId }: { accountId: number }) {
  const [offset, setOffset] = useState(0);
  const {
    data: page,
    error,
    mutate,
  } = useTransactions({
    account_id: accountId,
    limit: PAGE_SIZE,
    offset,
  });
  const { data: categories } = useCategories();

  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!page)
    return (
      <div aria-busy="true">
        {[1, 2, 3].map((row) => (
          <Skeleton key={row} className="medium" />
        ))}
      </div>
    );
  if (page.total === 0)
    return (
      <EmptyState
        title="Операций нет"
        description="По этому счёту пока нет операций."
        action={
          <Link className="button secondary" href="/transactions?new=1">
            Добавить операцию
          </Link>
        }
      />
    );

  const from = page.offset + 1;
  const to = page.offset + page.items.length;
  return (
    <>
      <ul className="account-transactions">
        {page.items.map((transaction) => {
          const sign = signForType(transaction.transaction_type);
          const category = categories?.find((item) => item.id === transaction.category_id);
          return (
            <li key={transaction.id}>
              <Link href={`/transactions/${transaction.id}`}>
                <span>{transaction.description || "Без описания"}</span>
                <span className={`tx-amount tabular-nums ${sign === "+" ? "text-positive" : ""}`}>
                  {formatMoney(transaction.amount, transaction.currency_code, { sign })}
                </span>
                <span className="tx-meta">
                  {category?.name ?? "Без категории"} · {formatDate(transaction.transaction_date)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="account-transactions-footer">
        <span>
          Показано {from}–{to} из {page.total}
        </span>
        <div>
          <button
            type="button"
            className="button secondary"
            disabled={page.offset === 0}
            onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}
          >
            Назад
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={to >= page.total}
            onClick={() => setOffset(page.offset + PAGE_SIZE)}
          >
            Вперёд
          </button>
        </div>
      </div>
    </>
  );
}
