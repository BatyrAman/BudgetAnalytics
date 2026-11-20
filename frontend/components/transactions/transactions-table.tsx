"use client";

import { formatDate, formatMoney, signForType } from "@/lib/format";
import type { Account, Bank, Category, Transaction } from "@/lib/types";

import { CategoryCell } from "./category-icon";
import { TYPE_LABELS } from "./filters";
import { toLocalDateInput } from "./period";

export type ReferenceData = {
  categories: Map<number, Category>;
  accounts: Map<number, Account>;
  banks: Map<number, Bank>;
};

function accountName(reference: ReferenceData, id: number | null) {
  if (id === null) return "—";
  return reference.accounts.get(id)?.name ?? "—";
}

function Amount({ transaction }: { transaction: Transaction }) {
  const sign = signForType(transaction.transaction_type);
  return (
    <span className={`tabular-nums ${sign === "+" ? "text-positive" : ""}`}>
      {formatMoney(transaction.amount, transaction.currency_code, { sign })}
    </span>
  );
}

function rowKeyHandler(onOpen: () => void) {
  return (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen();
    }
  };
}

/** Desktop and tablet tables (newest first; no sortable headers — G-7). */
export function TransactionsTable({
  items,
  reference,
  onOpen,
}: {
  items: Transaction[];
  reference: ReferenceData;
  onOpen: (transaction: Transaction) => void;
}) {
  return (
    <>
      <div className="table-scroll desktop-transaction-table">
        <table className="transactions-table">
          <caption className="sr-only">Операции, сначала новые</caption>
          <thead>
            <tr>
              <th scope="col">Дата</th>
              <th scope="col">Описание</th>
              <th scope="col">Категория</th>
              <th scope="col">Счёт</th>
              <th scope="col">Банк</th>
              <th scope="col" className="align-right">
                Сумма
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((transaction) => (
              <tr
                key={transaction.id}
                tabIndex={0}
                aria-label={`Открыть операцию: ${transaction.description || "Без описания"}`}
                onClick={() => onOpen(transaction)}
                onKeyDown={rowKeyHandler(() => onOpen(transaction))}
              >
                <td>{formatDate(transaction.transaction_date)}</td>
                <td>
                  <b>{transaction.description || "Без описания"}</b>
                  <small className="table-subline">
                    {TYPE_LABELS[transaction.transaction_type]}
                  </small>
                </td>
                <td>
                  <CategoryCell category={reference.categories.get(transaction.category_id)} />
                </td>
                <td>{accountName(reference, transaction.account_id)}</td>
                <td>
                  {transaction.bank_id === null
                    ? "—"
                    : (reference.banks.get(transaction.bank_id)?.name ?? "—")}
                </td>
                <td className="align-right">
                  <Amount transaction={transaction} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tablet-transaction-table">
        <table className="transactions-table">
          <thead>
            <tr>
              <th scope="col">Дата</th>
              <th scope="col">Описание и категория</th>
              <th scope="col" className="align-right">
                Сумма
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((transaction) => (
              <tr
                key={transaction.id}
                tabIndex={0}
                onClick={() => onOpen(transaction)}
                onKeyDown={rowKeyHandler(() => onOpen(transaction))}
              >
                <td>{formatDate(transaction.transaction_date)}</td>
                <td>
                  <b>{transaction.description || "Без описания"}</b>
                  <small className="table-subline">
                    {reference.categories.get(transaction.category_id)?.name ?? "—"}
                  </small>
                </td>
                <td className="align-right">
                  <Amount transaction={transaction} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** Mobile cards grouped by the local calendar day of the user's time zone. */
export function TransactionCards({
  items,
  reference,
  timeZone,
  onOpen,
}: {
  items: Transaction[];
  reference: ReferenceData;
  timeZone: string;
  onOpen: (transaction: Transaction) => void;
}) {
  const groups = new Map<string, Transaction[]>();
  for (const transaction of items) {
    const day = toLocalDateInput(transaction.transaction_date, timeZone);
    groups.set(day, [...(groups.get(day) ?? []), transaction]);
  }
  const dayLabel = new Intl.DateTimeFormat("ru-KZ", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  return (
    <div className="mobile-transaction-list">
      {Array.from(groups.entries()).map(([day, rows]) => (
        <div key={day}>
          <h3>{dayLabel.format(new Date(`${day}T12:00:00Z`)).replace(/\s*г\.$/, "")}</h3>
          {rows.map((transaction) => (
            <button
              type="button"
              className="mobile-transaction-card"
              key={transaction.id}
              onClick={() => onOpen(transaction)}
            >
              <span className="mobile-transaction-copy">
                <b>{transaction.description || "Без описания"}</b>
                <small>
                  {reference.categories.get(transaction.category_id)?.name ?? "—"} ·{" "}
                  {accountName(reference, transaction.account_id)}
                </small>
              </span>
              <strong>
                <Amount transaction={transaction} />
              </strong>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
