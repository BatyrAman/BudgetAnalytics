"use client";

import { useState } from "react";

import { ErrorState, Skeleton, StatusBadge } from "@/components/common";
import { useImportRows } from "@/lib/api/hooks";
import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import type { ImportRow, ImportSummary } from "@/lib/types";

import { TYPE_LABELS, type ListPage } from "./filters";
import { ROW_FILTERS, ROW_STATUS_LABELS, rowTone } from "./import-utils";
import { Pagination } from "./transactions-results";

const ROWS_PAGE_SIZE = 50;

/** Page of preview rows (`GET /imports/{id}/rows`). Key and fetcher are built together. */

export type RowSelection = {
  /** Row numbers the user unticked. */
  excluded: Set<number>;
  includePossibleDuplicates: boolean;
};

function selectable(row: ImportRow) {
  return row.status === "valid" || row.status === "possible_duplicate";
}

function RowCheckbox({
  row,
  selection,
  onToggle,
  withLabel,
}: {
  row: ImportRow;
  selection: RowSelection;
  onToggle: (row: ImportRow, include: boolean) => void;
  withLabel?: boolean;
}) {
  if (!selectable(row)) return null;
  const possible = row.status === "possible_duplicate";
  const disabled = possible && !selection.includePossibleDuplicates;
  const checked = !disabled && !selection.excluded.has(row.row_number);
  const input = (
    <input
      type="checkbox"
      aria-label={withLabel ? undefined : `Импортировать строку ${row.row_number}`}
      checked={checked}
      disabled={disabled}
      title={disabled ? "Включите «Импортировать возможные дубликаты»" : undefined}
      onChange={(event) => onToggle(row, event.target.checked)}
    />
  );
  return withLabel ? (
    <label className="exclude-row">
      {input}
      Импортировать строку {row.row_number}
    </label>
  ) : (
    input
  );
}

function amountText(row: ImportRow) {
  return row.amount && row.currency_code ? formatMoney(row.amount, row.currency_code) : "—";
}

/** I-1 step 3: summary, paged rows with status filter, exclusions and commit/cancel. */
export function ImportPreviewStep({
  summary,
  verified,
  bankName,
  selection,
  busy,
  onToggleRow,
  onIncludePossibleChange,
  onCommit,
  onCancel,
}: {
  summary: ImportSummary;
  verified: boolean;
  bankName: string;
  selection: RowSelection;
  busy: boolean;
  onToggleRow: (row: ImportRow, include: boolean) => void;
  onIncludePossibleChange: (include: boolean) => void;
  onCommit: () => void;
  onCancel: () => void;
}) {
  const [filterId, setFilterId] = useState("all");
  const [page, setPage] = useState<ListPage>({ limit: ROWS_PAGE_SIZE, offset: 0 });
  const status = ROW_FILTERS.find((item) => item.id === filterId)?.status;
  const { data, error, isLoading, mutate } = useImportRows(summary.id, {
    status,
    limit: ROWS_PAGE_SIZE,
    offset: page.offset,
  });
  const [nowMs] = useState(() => Date.now());
  const expired = summary.expires_at !== null && new Date(summary.expires_at).getTime() <= nowMs;

  return (
    <section className="import-panel preview-panel card-surface">
      <div className="preview-heading">
        <div>
          <h2>Проверьте операции</h2>
          <p className="muted-copy">
            {summary.file_name} · {bankName}
          </p>
        </div>
        {!verified && <StatusBadge tone="warning">Формат не проверен</StatusBadge>}
      </div>
      {!verified && (
        <div className="banner warning" role="note">
          Формат выписки этого банка ещё не проверен на реальных файлах. Внимательно проверьте
          строки перед импортом.
        </div>
      )}
      <div className="import-summary">
        <div>
          <b>{summary.total_rows}</b>
          <span>Всего строк</span>
        </div>
        <div>
          <b>{summary.valid_rows}</b>
          <span>Корректных</span>
        </div>
        <div>
          <b>{summary.invalid_rows}</b>
          <span>С ошибками</span>
        </div>
        <div>
          <b>{summary.duplicate_rows}</b>
          <span>Дубликатов</span>
        </div>
        <div>
          <b>
            {summary.period_start && summary.period_end
              ? `${formatDate(summary.period_start)} – ${formatDate(summary.period_end)}`
              : "—"}
          </b>
          <span>Период</span>
        </div>
      </div>
      <div className="import-row-tabs" role="group" aria-label="Фильтр строк">
        {ROW_FILTERS.map((item) => (
          <button
            type="button"
            className={filterId === item.id ? "selected" : ""}
            aria-pressed={filterId === item.id}
            key={item.id}
            onClick={() => {
              setFilterId(item.id);
              setPage({ limit: ROWS_PAGE_SIZE, offset: 0 });
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {error && !data ? (
        <ErrorState error={error} retry={() => void mutate()} />
      ) : isLoading && !data ? (
        <div aria-busy="true" aria-label="Загрузка строк">
          <Skeleton className="large" />
          <Skeleton className="large" />
          <Skeleton className="large" />
        </div>
      ) : data && data.items.length === 0 ? (
        <p className="muted-copy">Нет строк с таким статусом.</p>
      ) : data ? (
        <div className="preview-table-wrap">
          <table className="preview-table">
            <thead>
              <tr>
                <th scope="col">№</th>
                <th scope="col">Дата</th>
                <th scope="col">Описание / мерчант</th>
                <th scope="col">Тип</th>
                <th scope="col">Сумма</th>
                <th scope="col">Категория</th>
                <th scope="col">Статус</th>
                <th scope="col">Импорт</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.row_number}>
                  <td>{row.row_number}</td>
                  <td>{row.transaction_date ? formatDate(row.transaction_date) : "—"}</td>
                  <td>
                    <b>{row.description || row.merchant || "—"}</b>
                    {row.merchant && row.description && <small>{row.merchant}</small>}
                    {row.error_message && (
                      <small className="text-negative">{row.error_message}</small>
                    )}
                  </td>
                  <td>{row.transaction_type ? TYPE_LABELS[row.transaction_type] : "—"}</td>
                  <td className="tabular-nums">{amountText(row)}</td>
                  <td>{row.category_hint ?? "—"}</td>
                  <td>
                    <StatusBadge tone={rowTone(row.status)}>
                      {ROW_STATUS_LABELS[row.status]}
                    </StatusBadge>
                  </td>
                  <td>
                    <RowCheckbox row={row} selection={selection} onToggle={onToggleRow} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.items.map((row) => (
            <article className="preview-row-card" key={row.row_number}>
              <div className="preview-row-card-head">
                <b>Строка {row.row_number}</b>
                <StatusBadge tone={rowTone(row.status)}>
                  {ROW_STATUS_LABELS[row.status]}
                </StatusBadge>
              </div>
              <b>{row.description || row.merchant || "—"}</b>
              <span>
                {row.transaction_date ? formatDate(row.transaction_date) : "—"} · {amountText(row)}
              </span>
              {row.error_message && <small className="text-negative">{row.error_message}</small>}
              <RowCheckbox row={row} selection={selection} onToggle={onToggleRow} withLabel />
            </article>
          ))}
          <div className="import-row-pagination">
            <Pagination
              page={page}
              total={data.total}
              shown={data.items.length}
              note="По порядку строк в файле"
              onChange={(next) => setPage({ limit: ROWS_PAGE_SIZE, offset: next.offset })}
            />
          </div>
        </div>
      ) : null}
      <label className="check-sample import-check">
        <input
          type="checkbox"
          checked={selection.includePossibleDuplicates}
          onChange={(event) => onIncludePossibleChange(event.target.checked)}
        />
        Импортировать возможные дубликаты
      </label>
      {selection.excluded.size > 0 && (
        <p className="muted-copy">Исключено строк: {selection.excluded.size}</p>
      )}
      {summary.expires_at && (
        <p className={`preview-expiry ${expired ? "text-negative" : ""}`}>
          {expired
            ? `Срок предпросмотра истёк ${formatDateTime(summary.expires_at)}. Загрузите файл заново.`
            : `Предпросмотр действителен до ${formatDateTime(summary.expires_at)}`}
        </p>
      )}
      <div className="import-footer">
        <button type="button" className="button secondary" disabled={busy} onClick={onCancel}>
          Отменить импорт
        </button>
        <button
          type="button"
          className="button primary"
          disabled={
            busy || expired || (summary.valid_rows === 0 && !selection.includePossibleDuplicates)
          }
          onClick={onCommit}
        >
          {busy ? "Импортируем…" : "Импортировать операции"}
        </button>
      </div>
    </section>
  );
}
