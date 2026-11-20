import { ApiError } from "@/lib/api/errors";
import type { ImportRow, ImportSummary } from "@/lib/types";

/** Same limit as backend `IMPORT_MAX_FILE_BYTES`. */
export const MAX_IMPORT_FILE_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ["csv", "xlsx"];

/**
 * Client-side file check before upload. Returns an `ApiError` with the same
 * machine code the backend would use, so `toUserMessage` gives the same text.
 */
export function checkImportFile(file: File): ApiError | null {
  const extension = file.name.includes(".") ? file.name.split(".").pop()?.toLowerCase() : "";
  if (extension === "pdf") return new ApiError({ status: 415, code: "pdf_not_supported" });
  if (!extension || !ALLOWED_EXTENSIONS.includes(extension))
    return new ApiError({ status: 415, code: "unsupported_format" });
  if (file.size > MAX_IMPORT_FILE_BYTES)
    return new ApiError({ status: 413, code: "file_too_large" });
  if (file.size === 0) return new ApiError({ status: 400, code: "empty_file" });
  return null;
}

/** File size in KB/MB for display (not a financial value). */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} МБ`;
}

export const ROW_STATUS_LABELS: Record<ImportRow["status"], string> = {
  valid: "Корректная",
  invalid: "С ошибкой",
  duplicate: "Дубликат",
  possible_duplicate: "Возможный дубликат",
  imported: "Импортирована",
  skipped: "Пропущена",
};

export function rowTone(status: ImportRow["status"]) {
  if (status === "valid" || status === "imported") return "positive" as const;
  if (status === "invalid") return "negative" as const;
  if (status === "possible_duplicate") return "warning" as const;
  return "neutral" as const;
}

export const ROW_FILTERS: { id: string; label: string; status?: ImportRow["status"] }[] = [
  { id: "all", label: "Все" },
  { id: "valid", label: "Корректные", status: "valid" },
  { id: "invalid", label: "С ошибками", status: "invalid" },
  { id: "duplicate", label: "Дубликаты", status: "duplicate" },
  { id: "possible_duplicate", label: "Возможные дубликаты", status: "possible_duplicate" },
];

export const IMPORT_STATUS_LABELS: Record<ImportSummary["status"], string> = {
  preview: "Предпросмотр",
  committed: "Импортирован",
  failed: "Ошибка",
  cancelled: "Отменён",
  expired: "Истёк",
};

export function importTone(status: ImportSummary["status"]) {
  if (status === "committed") return "positive" as const;
  if (status === "failed") return "negative" as const;
  if (status === "preview") return "warning" as const;
  return "neutral" as const;
}
