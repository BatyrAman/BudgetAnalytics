"use client";

import { useState } from "react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, Skeleton, StatusBadge } from "@/components/common";
import { useImportBanks, useImports } from "@/lib/api/hooks";
import { formatDate, formatDateTime } from "@/lib/format";
import { usePreviewState } from "@/lib/preview";

import { DEFAULT_PAGE_SIZE, type ListPage } from "./filters";
import { IMPORT_STATUS_LABELS, importTone } from "./import-utils";
import { Pagination } from "./transactions-results";

/** I-2: paginated history of statement imports (`GET /imports`). */
export function ImportHistory() {
  const preview = usePreviewState();
  const [page, setPage] = useState<ListPage>({ limit: DEFAULT_PAGE_SIZE, offset: 0 });
  const { data, error, isLoading, mutate } = useImports(page);
  const { data: banks } = useImportBanks();
  const bankName = (code: string) => banks?.find((bank) => bank.code === code)?.name ?? code;
  const items = preview === "empty" ? [] : (data?.items ?? []);

  let body: React.ReactNode;
  if (preview === "error" || (error && !data)) {
    body = (
      <section className="card-surface">
        <ErrorState error={preview === "error" ? undefined : error} retry={() => void mutate()} />
      </section>
    );
  } else if (preview === "loading" || (isLoading && !data) || !data) {
    body = (
      <section
        className="card-surface loading-history"
        aria-busy="true"
        aria-label="Загрузка истории импортов"
      >
        <Skeleton className="medium" />
        <Skeleton className="large" />
        <Skeleton className="medium" />
      </section>
    );
  } else if (items.length === 0 && page.offset === 0) {
    body = (
      <section className="card-surface">
        <EmptyState
          title="Импортов пока нет"
          description="Загруженные выписки появятся здесь."
          action={
            <Link className="button primary" href="/transactions/import">
              Импортировать выписку
            </Link>
          }
        />
      </section>
    );
  } else {
    body = (
      <section className="transaction-table card-surface">
        <div className="table-scroll import-history-scroll">
          <table className="transactions-table import-history-table">
            <thead>
              <tr>
                <th scope="col">Файл</th>
                <th scope="col">Банк</th>
                <th scope="col">Статус</th>
                <th scope="col">Строки</th>
                <th scope="col">Период</th>
                <th scope="col">Дата</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <b>{item.file_name}</b>
                    {item.status === "failed" && item.error_message && (
                      <small className="text-negative">{item.error_message}</small>
                    )}
                    {item.status === "preview" && item.expires_at && (
                      <small className="table-subline">
                        Предпросмотр до {formatDateTime(item.expires_at)}
                      </small>
                    )}
                  </td>
                  <td>{bankName(item.bank)}</td>
                  <td>
                    <StatusBadge tone={importTone(item.status)}>
                      {IMPORT_STATUS_LABELS[item.status]}
                    </StatusBadge>
                  </td>
                  <td>
                    {item.status === "committed"
                      ? `${item.imported_rows} из ${item.total_rows} импортировано`
                      : `${item.total_rows} строк`}
                  </td>
                  <td>
                    {item.period_start && item.period_end
                      ? `${formatDate(item.period_start)} – ${formatDate(item.period_end)}`
                      : "—"}
                  </td>
                  <td>{formatDateTime(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination page={page} total={data.total} shown={items.length} onChange={setPage} />
      </section>
    );
  }

  return (
    <AppShell>
      <div className="import-page">
        <PageHeader
          title="История импортов"
          description="Файлы и результаты загрузки выписок"
          actions={
            <Link className="button secondary" href="/transactions/import">
              Новый импорт
            </Link>
          }
        />
        {body}
      </div>
    </AppShell>
  );
}
