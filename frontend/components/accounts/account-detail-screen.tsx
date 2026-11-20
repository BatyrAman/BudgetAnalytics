"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { MoreHorizontal, Wallet } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { BackendBadge, ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { updateAccount } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useAccount, useBanks } from "@/lib/api/hooks";
import { formatDate, formatMoney } from "@/lib/format";
import type { Account } from "@/lib/types";
import { AccountFormDialog } from "./account-form";
import { accountDependentKey, accountTypeLabels } from "./account-meta";
import { AccountTransactions } from "./account-transactions";
import { DeleteAccountDialog } from "./delete-account-dialog";
import "./accounts.css";

export function AccountDetailContent({ id }: { id: number }) {
  const validId = Number.isInteger(id) && id > 0 ? id : null;
  const router = useRouter();
  const { mutate: globalMutate } = useSWRConfig();
  const { data: account, error, mutate } = useAccount(validId);
  const { data: banks = [] } = useBanks();
  const [menu, setMenu] = useState(false);
  const [dialog, setDialog] = useState<"edit" | "delete" | null>(null);
  const [notice, setNotice] = useState<{ text: string; tone: "status" | "alert" } | null>(null);

  if (validId === null || (error instanceof ApiError && error.status === 404))
    return (
      <ErrorState
        title="Счёт не найден"
        error={error ?? new ApiError({ status: 404, code: "account_not_found" })}
      />
    );
  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!account)
    return (
      <div className="account-grid" aria-busy="true">
        <SkeletonCard />
      </div>
    );

  const refresh = () => globalMutate(accountDependentKey);
  const bank = banks.find((item) => item.id === account.bank_id);

  async function toggleArchive(current: Account) {
    const updated = await updateAccount(current.id, { is_archived: !current.is_archived });
    await mutate(updated, { revalidate: false });
    await refresh();
    setNotice({
      text: updated.is_archived ? "Счёт перемещён в архив" : "Счёт возвращён из архива",
      tone: "status",
    });
  }

  async function archiveFromMenu() {
    setMenu(false);
    try {
      await toggleArchive(account as Account);
    } catch (failure) {
      setNotice({ text: toUserMessage(failure), tone: "alert" });
    }
  }

  const negative = account.balance.trim().startsWith("-");
  return (
    <div className="entity-page">
      <div className="account-detail-heading">
        <div>
          <Link href="/accounts" className="back-link">
            ← Все счета
          </Link>
          <PageHeader
            title={account.name}
            description={`${accountTypeLabels[account.account_type]} · ${bank?.name ?? "Без банка"}${account.last4 ? ` · •• ${account.last4}` : ""} · ${account.currency_code}${account.is_archived ? " · в архиве" : ""}`}
            actions={
              <>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setDialog("edit")}
                >
                  Изменить
                </button>
                <div className="entity-menu-wrap">
                  <button
                    type="button"
                    className="button secondary icon-button"
                    aria-label="Действия со счётом"
                    aria-haspopup="menu"
                    aria-expanded={menu}
                    onClick={() => setMenu(!menu)}
                  >
                    <MoreHorizontal aria-hidden="true" />
                  </button>
                  {menu && (
                    <div className="entity-menu" role="menu">
                      <button type="button" role="menuitem" onClick={() => void archiveFromMenu()}>
                        {account.is_archived ? "Вернуть из архива" : "Архивировать"}
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        className="text-negative"
                        onClick={() => {
                          setMenu(false);
                          setDialog("delete");
                        }}
                      >
                        Удалить
                      </button>
                    </div>
                  )}
                </div>
              </>
            }
          />
        </div>
      </div>
      {notice && (
        <p className="inline-notice" role={notice.tone}>
          {notice.text}
        </p>
      )}
      <div className="account-summary-grid">
        <section className="card-surface account-summary">
          <span>Баланс</span>
          <strong className={negative ? "text-negative" : ""}>
            {formatMoney(account.balance, account.currency_code)}
          </strong>
        </section>
        <section className="card-surface account-summary">
          <span>Начальный остаток</span>
          <strong>{formatMoney(account.opening_balance, account.currency_code)}</strong>
          <small>На {formatDate(account.opening_balance_at)}</small>
        </section>
      </div>
      <p className="balance-formula">
        Баланс = начальный остаток + поступления − списания после даты начального остатка
        (рассчитывает сервер)
      </p>
      <section className="entity-section">
        <header>
          <h2>Операции счёта</h2>
          <Link href={`/transactions?account_id=${account.id}`}>Открыть все</Link>
        </header>
        <AccountTransactions accountId={account.id} />
      </section>
      <section className="backend-note card-surface">
        <div>
          <Wallet aria-hidden="true" />
          <div>
            <b>Динамика баланса по дням</b>
            <p>Появится после доработки backend</p>
          </div>
        </div>
        <BackendBadge />
      </section>
      {dialog === "delete" && (
        <DeleteAccountDialog
          accountId={account.id}
          isArchived={account.is_archived}
          onClose={() => setDialog(null)}
          onDeleted={async () => {
            setDialog(null);
            router.push("/accounts");
            await refresh();
          }}
          onArchive={async () => {
            await toggleArchive(account);
            setDialog(null);
          }}
        />
      )}
      {dialog === "edit" && (
        <AccountFormDialog
          account={account}
          onClose={() => setDialog(null)}
          onSaved={async (saved) => {
            setDialog(null);
            await mutate(saved, { revalidate: false });
            await refresh();
            setNotice({ text: "Изменения сохранены", tone: "status" });
          }}
        />
      )}
    </div>
  );
}

export function AccountDetailScreen({ id }: { id: number }) {
  return (
    <AppShell>
      <AccountDetailContent id={id} />
    </AppShell>
  );
}
