"use client";

import { useState } from "react";
import Link from "next/link";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Check, Upload, X } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/common";
import { commitImport, deleteImport, previewImport, type ImportPreview } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useAccounts, useImportBanks } from "@/lib/api/hooks";
import type { ImportBank, ImportRow } from "@/lib/types";

import { ConfirmDialog } from "./confirm-dialog";
import { ImportPreviewStep, type RowSelection } from "./import-preview-step";
import { checkImportFile, formatFileSize } from "./import-utils";
import { isTransactionDependentKey } from "./revalidate";
import "./transactions.css";

const STEPS = ["Банк и счёт", "Файл", "Предпросмотр", "Итог"];
/** Commit/cancel codes after which the preview cannot be used any more. */
const DEAD_PREVIEW_CODES = new Set([
  "import_expired",
  "import_not_committable",
  "import_not_found",
]);

function Banner({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="banner error import-error" role="alert">
      <span>{message}</span>
      <button
        type="button"
        className="icon-button"
        aria-label="Закрыть сообщение"
        onClick={onClose}
      >
        <X />
      </button>
    </div>
  );
}

function BankStep({
  bank,
  accountId,
  onBank,
  onAccount,
  onNext,
}: {
  bank: ImportBank | null;
  accountId: string;
  onBank: (bank: ImportBank) => void;
  onAccount: (id: string) => void;
  onNext: () => void;
}) {
  const banks = useImportBanks();
  const accounts = useAccounts(false);
  const anyUnverified = banks.data?.some((item) => !item.verified) ?? false;
  return (
    <section className="import-panel card-surface">
      <h2>Выберите банк</h2>
      {anyUnverified && (
        <p className="muted-copy">
          Некоторые форматы выписок пока не проверены на реальных файлах.
        </p>
      )}
      {banks.error ? (
        <ErrorState error={banks.error} retry={() => void banks.mutate()} />
      ) : !banks.data ? (
        <div className="import-bank-grid" aria-busy="true">
          {[1, 2, 3].map((item) => (
            <div className="import-bank-card" key={item}>
              <Skeleton className="medium" />
            </div>
          ))}
        </div>
      ) : banks.data.length === 0 ? (
        <EmptyState description="Импорт выписок пока недоступен ни для одного банка." />
      ) : (
        <div className="import-bank-grid">
          {banks.data.map((item) => (
            <button
              type="button"
              className={`import-bank-card ${bank?.code === item.code ? "selected" : ""}`}
              key={item.code}
              onClick={() => onBank(item)}
              aria-pressed={bank?.code === item.code}
            >
              <span className={`bank-logo bank-${item.code}`} aria-hidden="true">
                {item.name.slice(0, 1).toUpperCase()}
              </span>
              <b>{item.name}</b>
              {item.verified ? (
                <small className="verified">Формат проверен</small>
              ) : (
                <small>Формат не проверен</small>
              )}
              <small>{item.formats.map((format) => format.toUpperCase()).join(", ")}</small>
            </button>
          ))}
        </div>
      )}
      <label className="field-label import-account">
        Счёт (необязательно)
        <select value={accountId} onChange={(event) => onAccount(event.target.value)}>
          <option value="">Не выбран</option>
          {(accounts.data ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} · {account.currency_code}
            </option>
          ))}
        </select>
      </label>
      <div className="import-footer">
        <span />
        <button type="button" className="button primary" disabled={!bank} onClick={onNext}>
          Продолжить <ArrowRight aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

function FileStep({
  bankName,
  file,
  busy,
  onFile,
  onBack,
  onPreview,
}: {
  bankName: string;
  file: File | null;
  busy: boolean;
  onFile: (file: File) => void;
  onBack: () => void;
  onPreview: () => void;
}) {
  return (
    <section className="import-panel card-surface">
      <h2>Загрузите выписку</h2>
      <p className="muted-copy">{bankName} · CSV или XLSX</p>
      <label
        className="upload-zone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          const dropped = event.dataTransfer.files[0];
          if (dropped) onFile(dropped);
        }}
      >
        <input
          type="file"
          accept=".csv,.xlsx"
          aria-label="Файл выписки"
          onChange={(event) => {
            const selected = event.target.files?.[0];
            if (selected) onFile(selected);
            event.target.value = "";
          }}
        />
        <span aria-hidden="true">
          <Upload />
        </span>
        <b>{file ? file.name : "Перетащите файл сюда или выберите на устройстве"}</b>
        <small>CSV или XLSX, до 5 МБ, до 5000 строк</small>
        {file && <small>{formatFileSize(file.size)} · файл готов к проверке</small>}
      </label>
      <div className="import-footer">
        <button type="button" className="button secondary" onClick={onBack} disabled={busy}>
          <ArrowLeft aria-hidden="true" /> Назад
        </button>
        <button
          type="button"
          className="button primary"
          disabled={!file || busy}
          onClick={onPreview}
        >
          {busy ? "Загружаем…" : "Предпросмотр"} <ArrowRight aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}

const emptySelection = (): RowSelection => ({
  excluded: new Set(),
  includePossibleDuplicates: false,
});

/** I-1: statement import wizard (bank → file → preview → result). */
export function ImportWizard() {
  const { mutate } = useSWRConfig();
  const [step, setStep] = useState(1);
  const [bank, setBank] = useState<ImportBank | null>(null);
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [selection, setSelection] = useState<RowSelection>(emptySelection);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [deadPreview, setDeadPreview] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null);

  const revalidate = () =>
    mutate(
      (key: unknown) =>
        isTransactionDependentKey(key) || (Array.isArray(key) && key[0] === "imports"),
    );

  function chooseFile(selected: File) {
    const rejection = checkImportFile(selected);
    if (rejection) {
      setFile(null);
      setMessage(toUserMessage(rejection));
      return;
    }
    setMessage("");
    setFile(selected);
  }

  function restartUpload() {
    setPreview(null);
    setSelection(emptySelection());
    setFile(null);
    setDeadPreview(false);
    setStep(2);
  }

  async function loadPreview() {
    if (!bank || !file) return;
    const rejection = checkImportFile(file);
    if (rejection) return setMessage(toUserMessage(rejection));
    setBusy(true);
    setMessage("");
    try {
      const response = await previewImport(bank.code, file, accountId ? Number(accountId) : null);
      setPreview(response);
      setSelection(emptySelection());
      setDeadPreview(false);
      setStep(3);
      void mutate((key: unknown) => Array.isArray(key) && key[0] === "imports");
    } catch (error) {
      setMessage(toUserMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!preview) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await commitImport(preview.import.id, {
        exclude_rows: Array.from(selection.excluded).sort((a, b) => a - b),
        include_possible_duplicates: selection.includePossibleDuplicates,
      });
      setResult({ imported: response.imported, skipped: response.skipped });
      setStep(4);
      toast.success("Импорт завершён");
      void revalidate();
    } catch (error) {
      setMessage(toUserMessage(error));
      if (error instanceof ApiError && DEAD_PREVIEW_CODES.has(error.code)) setDeadPreview(true);
    } finally {
      setBusy(false);
    }
  }

  async function cancelImport() {
    if (!preview) return;
    setBusy(true);
    try {
      await deleteImport(preview.import.id);
      setConfirmCancel(false);
      setMessage("");
      toast.success("Импорт отменён");
      void mutate((key: unknown) => Array.isArray(key) && key[0] === "imports");
      restartUpload();
    } catch (error) {
      setConfirmCancel(false);
      setMessage(toUserMessage(error));
      if (
        error instanceof ApiError &&
        (error.code === "import_not_cancellable" || error.status === 404)
      )
        setDeadPreview(true);
    } finally {
      setBusy(false);
    }
  }

  function toggleRow(row: ImportRow, include: boolean) {
    setSelection((current) => {
      const excluded = new Set(current.excluded);
      if (include) excluded.delete(row.row_number);
      else excluded.add(row.row_number);
      return { ...current, excluded };
    });
  }

  function startOver() {
    setStep(1);
    setBank(null);
    setAccountId("");
    setFile(null);
    setPreview(null);
    setSelection(emptySelection());
    setResult(null);
    setMessage("");
    setDeadPreview(false);
  }

  return (
    <AppShell>
      <div className="import-page">
        <PageHeader
          title="Импорт выписки"
          description="Загрузите файл и проверьте операции перед добавлением"
          actions={
            <Link className="button secondary" href="/transactions/import/history">
              История импортов
            </Link>
          }
        />
        <div className="import-steps" role="list" aria-label="Шаги импорта">
          {STEPS.map((label, index) => (
            <div
              role="listitem"
              className={step >= index + 1 ? "active" : ""}
              key={label}
              aria-current={step === index + 1 ? "step" : undefined}
            >
              <span>{step > index + 1 ? <Check aria-label="Готово" /> : index + 1}</span>
              <b>{label}</b>
            </div>
          ))}
        </div>
        {message && <Banner message={message} onClose={() => setMessage("")} />}
        {deadPreview && (
          <div className="import-footer">
            <span />
            <button type="button" className="button primary" onClick={restartUpload}>
              Загрузить файл заново
            </button>
          </div>
        )}
        {step === 1 && (
          <BankStep
            bank={bank}
            accountId={accountId}
            onBank={setBank}
            onAccount={setAccountId}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && bank && (
          <FileStep
            bankName={bank.name}
            file={file}
            busy={busy}
            onFile={chooseFile}
            onBack={() => {
              setMessage("");
              setStep(1);
            }}
            onPreview={() => void loadPreview()}
          />
        )}
        {step === 3 && preview && (
          <ImportPreviewStep
            summary={preview.import}
            verified={preview.verified_parser}
            bankName={bank?.name ?? preview.import.bank}
            selection={selection}
            busy={busy || deadPreview}
            onToggleRow={toggleRow}
            onIncludePossibleChange={(include) =>
              setSelection((current) => ({ ...current, includePossibleDuplicates: include }))
            }
            onCommit={() => void finish()}
            onCancel={() => setConfirmCancel(true)}
          />
        )}
        {step === 4 && result && (
          <section className="import-panel import-result card-surface">
            <span className="result-mark" aria-hidden="true">
              <Check />
            </span>
            <h2>Импорт завершён</h2>
            <p>
              Импортировано {result.imported}, пропущено {result.skipped}
            </p>
            <div className="dialog-actions">
              <Link className="button primary" href="/transactions">
                Перейти к операциям
              </Link>
              <button type="button" className="button secondary" onClick={startOver}>
                Импортировать ещё
              </button>
            </div>
          </section>
        )}
        {confirmCancel && (
          <ConfirmDialog
            title="Отменить импорт?"
            description="Предпросмотр будет удалён, операции не добавятся."
            confirmLabel={busy ? "Отменяем…" : "Отменить импорт"}
            cancelLabel="Вернуться"
            danger
            busy={busy}
            onConfirm={() => void cancelImport()}
            onCancel={() => setConfirmCancel(false)}
          />
        )}
      </div>
    </AppShell>
  );
}
