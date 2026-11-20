"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSWRConfig } from "swr";
import { Plus } from "lucide-react";
import { AppShell, StatePreviewSwitcher } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, Skeleton, SkeletonCard } from "@/components/common";
import { useAccounts, useBanks, useDefaultCurrency, useOverview } from "@/lib/api/hooks";
import { formatDate, formatMoney } from "@/lib/format";
import { usePreviewState } from "@/lib/preview";
import type { Account, Bank } from "@/lib/types";
import { AccountFormDialog } from "./account-form";
import {
  accountDependentKey,
  accountTypeIcons,
  accountTypeLabels,
  orderCurrencies,
} from "./account-meta";
import "./accounts.css";

/** Group total — ONLY from the backend overview (`current_balance`), never summed in the browser. */
function GroupTotal({ currency }: { currency: string }) {
  const { data, error, mutate } = useOverview(currency);
  if (error)
    return (
      <span className="group-total-error">
        Итог недоступен{" "}
        <button type="button" className="text-link" onClick={() => void mutate()}>
          Повторить
        </button>
      </span>
    );
  if (!data) return <Skeleton className="short" />;
  if (data.current_balance == null)
    return (
      <strong title={`Нет активных счетов в ${currency}`} data-testid={`group-total-${currency}`}>
        —
      </strong>
    );
  return (
    <strong data-testid={`group-total-${currency}`}>
      {formatMoney(data.current_balance, data.currency_code)}
    </strong>
  );
}

function AccountCard({ account, bank }: { account: Account; bank?: Bank }) {
  const Icon = accountTypeIcons[account.account_type];
  // Sign check for colouring only.
  const negative = account.balance.trim().startsWith("-");
  return (
    <Link
      className={`account-card card-surface ${account.is_archived ? "is-archived" : ""}`}
      href={`/accounts/${account.id}`}
    >
      <div className="account-card-top">
        <span className="account-type-icon" aria-hidden="true">
          <Icon />
        </span>
        {account.is_archived && <span className="status-badge tone-neutral">В архиве</span>}
      </div>
      <h3>{account.name}</h3>
      <p className="account-kind">{accountTypeLabels[account.account_type]}</p>
      <div className="account-bank">
        <span className="bank-initials" aria-hidden="true">
          {bank?.name.slice(0, 2).toUpperCase() ?? "—"}
        </span>
        <span>{bank?.name ?? "Без банка"}</span>
        {account.last4 && <span className="last4">•• {account.last4}</span>}
      </div>
      <strong className={`account-balance ${negative ? "text-negative" : ""}`}>
        {formatMoney(account.balance, account.currency_code)}
      </strong>
      <small>
        Начальный остаток {formatMoney(account.opening_balance, account.currency_code)} на{" "}
        {formatDate(account.opening_balance_at)}
      </small>
    </Link>
  );
}

function AccountsContent() {
  const preview = usePreviewState();
  const [archived, setArchived] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const { mutate: globalMutate } = useSWRConfig();
  const defaultCurrency = useDefaultCurrency();
  const { data: accounts, error, mutate } = useAccounts(archived);
  const { data: banks = [] } = useBanks();

  const currencies = orderCurrencies(
    (accounts ?? []).map((account) => account.currency_code),
    defaultCurrency,
  );
  const openForm = () => setFormOpen(true);

  let body: React.ReactNode;
  if (preview === "error") body = <ErrorState retry={() => void mutate()} />;
  else if (error) body = <ErrorState error={error} retry={() => void mutate()} />;
  else if (preview === "loading" || !accounts)
    body = (
      <div className="account-grid" aria-busy="true">
        {[1, 2, 3].map((item) => (
          <SkeletonCard key={item} />
        ))}
      </div>
    );
  else if (preview === "empty" || accounts.length === 0)
    body = (
      <EmptyState
        title={archived ? "Счетов нет" : "Добавьте первый счёт"}
        description="Баланс будет считаться из начального остатка и операций"
        action={
          <button type="button" className="button primary" onClick={openForm}>
            Добавить счёт
          </button>
        }
      />
    );
  else
    body = currencies.map((currency) => (
      <section className="account-group" key={currency} aria-label={`Счета в ${currency}`}>
        <header className="account-group-heading">
          <div>
            <h2>{currency}</h2>
            <p>Баланс активных счетов в {currency}</p>
          </div>
          <GroupTotal currency={currency} />
        </header>
        <div className="account-grid">
          {accounts
            .filter((account) => account.currency_code === currency)
            .map((account) => (
              <AccountCard
                key={account.id}
                account={account}
                bank={banks.find((bank) => bank.id === account.bank_id)}
              />
            ))}
        </div>
      </section>
    ));

  return (
    <div className="entity-page">
      <div className="state-row">
        <StatePreviewSwitcher />
      </div>
      <PageHeader
        title="Счета"
        description="Баланс, начальные остатки и состояние счетов"
        actions={
          <button type="button" className="button primary" onClick={openForm}>
            <Plus aria-hidden="true" />
            Добавить счёт
          </button>
        }
      />
      <label className="archive-toggle">
        <input
          type="checkbox"
          checked={archived}
          onChange={(event) => setArchived(event.target.checked)}
        />
        Показать архивные
      </label>
      {body}
      {formOpen && (
        <AccountFormDialog
          onClose={() => setFormOpen(false)}
          onSaved={async () => {
            setFormOpen(false);
            await globalMutate(accountDependentKey);
          }}
        />
      )}
    </div>
  );
}

export function AccountsScreen() {
  return (
    <AppShell>
      <Suspense fallback={<div className="state-row">Загрузка счетов…</div>}>
        <AccountsContent />
      </Suspense>
    </AppShell>
  );
}

export { AccountsContent };
