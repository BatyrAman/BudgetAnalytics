import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import type { ImportRow, ImportSummary } from "@/lib/types";

import { ImportHistory } from "./import-history";
import { ImportWizard } from "./import-wizard";
import { account, apiError, page, renderWithSWR } from "./test-utils";

vi.mock("next/navigation", async () => (await import("./test-utils")).navigationMock());
vi.mock("@/components/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  listImportBanks: vi.fn(),
  listAccounts: vi.fn(),
  previewImport: vi.fn(),
  listImportRows: vi.fn(),
  commitImport: vi.fn(),
  deleteImport: vi.fn(),
  listImports: vi.fn(),
}));

const api = vi.mocked(client);

function summary(overrides: Partial<ImportSummary> = {}): ImportSummary {
  return {
    id: 7,
    bank: "kaspi",
    file_name: "statement.csv",
    file_format: "csv",
    file_size: 1200,
    status: "preview",
    account_id: null,
    total_rows: 3,
    valid_rows: 2,
    invalid_rows: 0,
    duplicate_rows: 1,
    imported_rows: 0,
    period_start: "2026-11-01T00:00:00Z",
    period_end: "2026-11-15T00:00:00Z",
    error_message: null,
    created_at: "2026-11-19T05:00:00Z",
    expires_at: "2099-01-01T00:00:00Z",
    ...overrides,
  };
}

function row(row_number: number, status: ImportRow["status"]): ImportRow {
  return {
    row_number,
    status,
    transaction_date: "2026-11-05T10:00:00Z",
    amount: "1500.00",
    currency_code: "KZT",
    transaction_type: "expense",
    description: `Строка ${row_number}`,
    merchant: null,
    category_hint: null,
    error_message: null,
  };
}

beforeEach(() => {
  api.listImportBanks.mockResolvedValue([
    { code: "kaspi", name: "Kaspi Bank", formats: ["csv"], verified: false },
  ]);
  api.listAccounts.mockResolvedValue([account()]);
});

async function toFileStep(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /Kaspi Bank/ }));
  expect(screen.getByText("Формат не проверен")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Продолжить/ }));
}

function csv(name = "statement.csv", size?: number) {
  const file = new File(["date;amount\n"], name, { type: "text/csv" });
  if (size !== undefined) Object.defineProperty(file, "size", { value: size });
  return file;
}

async function toPreview(user: ReturnType<typeof userEvent.setup>) {
  api.previewImport.mockResolvedValue({ import: summary(), rows: [], verified_parser: false });
  api.listImportRows.mockResolvedValue(
    page([row(1, "valid"), row(2, "valid"), row(3, "possible_duplicate")], 3, 50),
  );
  renderWithSWR(<ImportWizard />);
  await toFileStep(user);
  const file = csv();
  await user.upload(screen.getByLabelText("Файл выписки"), file);
  await user.click(screen.getByRole("button", { name: /Предпросмотр/ }));
  await screen.findByRole("heading", { name: "Проверьте операции" });
  expect(api.previewImport).toHaveBeenCalledWith("kaspi", file, null);
}

describe("ImportWizard (I-1)", () => {
  it("rejects a 6 MB file on the client without calling the API", async () => {
    const user = userEvent.setup();
    renderWithSWR(<ImportWizard />);
    await toFileStep(user);

    await user.upload(screen.getByLabelText("Файл выписки"), csv("big.csv", 6 * 1024 * 1024));

    expect(await screen.findByRole("alert")).toHaveTextContent("Файл больше 5 МБ.");
    expect(screen.getByRole("button", { name: /Предпросмотр/ })).toBeDisabled();
    expect(api.previewImport).not.toHaveBeenCalled();
  });

  it("rejects PDF with the pdf_not_supported message", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderWithSWR(<ImportWizard />);
    await toFileStep(user);
    await user.upload(
      screen.getByLabelText("Файл выписки"),
      new File(["%PDF"], "s.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "PDF не поддерживается — выгрузите выписку в CSV или XLSX.",
    );
    expect(api.previewImport).not.toHaveBeenCalled();
  });

  it("shows a FileRejected code from the backend in Russian", async () => {
    const user = userEvent.setup();
    api.previewImport.mockRejectedValue(apiError(422, "format_mismatch"));
    renderWithSWR(<ImportWizard />);
    await toFileStep(user);
    await user.upload(screen.getByLabelText("Файл выписки"), csv());
    await user.click(screen.getByRole("button", { name: /Предпросмотр/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Файл не похож на выписку выбранного банка. Проверьте банк или формат.",
    );
  });

  it("previews, excludes a row, includes possible duplicates and commits", async () => {
    const user = userEvent.setup();
    api.commitImport.mockResolvedValue({
      import: summary({ status: "committed" }),
      imported: 2,
      skipped: 1,
    });
    await toPreview(user);

    expect(api.listImportRows).toHaveBeenCalledWith(7, { status: undefined, limit: 50, offset: 0 });
    expect(screen.getByText(/Формат выписки этого банка ещё не проверен/)).toBeInTheDocument();
    expect(screen.getByText(/Предпросмотр действителен до/)).toBeInTheDocument();

    const table = screen.getAllByRole("table")[0];
    await user.click(within(table).getByLabelText("Импортировать строку 2"));
    expect(within(table).getByLabelText("Импортировать строку 3")).toBeDisabled();
    await user.click(screen.getByLabelText("Импортировать возможные дубликаты"));
    expect(within(table).getByLabelText("Импортировать строку 3")).toBeChecked();

    await user.click(screen.getByRole("button", { name: "Импортировать операции" }));
    await waitFor(() =>
      expect(api.commitImport).toHaveBeenCalledWith(7, {
        exclude_rows: [2],
        include_possible_duplicates: true,
      }),
    );
    expect(await screen.findByText("Импортировано 2, пропущено 1")).toBeInTheDocument();
  });

  it("filters preview rows by status through the API", async () => {
    const user = userEvent.setup();
    await toPreview(user);
    await user.click(screen.getByRole("button", { name: "С ошибками" }));
    await waitFor(() =>
      expect(api.listImportRows).toHaveBeenLastCalledWith(7, {
        status: "invalid",
        limit: 50,
        offset: 0,
      }),
    );
  });

  it("shows the Russian message for import_expired and offers a new upload", async () => {
    const user = userEvent.setup();
    api.commitImport.mockRejectedValue(apiError(409, "import_expired"));
    await toPreview(user);
    await user.click(screen.getByRole("button", { name: "Импортировать операции" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Срок предпросмотра истёк (24 ч). Загрузите файл заново.",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить файл заново" }));
    expect(screen.getByRole("heading", { name: "Загрузите выписку" })).toBeInTheDocument();
  });

  it("cancels a preview via DELETE after confirmation", async () => {
    const user = userEvent.setup();
    api.deleteImport.mockResolvedValue(undefined);
    await toPreview(user);
    await user.click(screen.getByRole("button", { name: "Отменить импорт" }));
    const dialog = screen.getByRole("alertdialog", { name: "Отменить импорт?" });
    await user.click(within(dialog).getByRole("button", { name: "Отменить импорт" }));
    await waitFor(() => expect(api.deleteImport).toHaveBeenCalledWith(7));
    expect(await screen.findByRole("heading", { name: "Загрузите выписку" })).toBeInTheDocument();
  });

  it("maps import_not_cancellable to a Russian message", async () => {
    const user = userEvent.setup();
    api.deleteImport.mockRejectedValue(apiError(409, "import_not_cancellable"));
    await toPreview(user);
    await user.click(screen.getByRole("button", { name: "Отменить импорт" }));
    const dialog = screen.getByRole("alertdialog", { name: "Отменить импорт?" });
    await user.click(within(dialog).getByRole("button", { name: "Отменить импорт" }));
    expect(await screen.findByText("Этот импорт уже нельзя отменить.")).toBeInTheDocument();
  });
});

describe("ImportHistory (I-2)", () => {
  it("paginates, shows Russian statuses and error_message only for failed imports", async () => {
    const user = userEvent.setup();
    api.listImports.mockResolvedValue(
      page(
        [
          summary({ id: 1, status: "failed", error_message: "В файле не найдено операций." }),
          summary({
            id: 2,
            file_name: "ok.csv",
            status: "committed",
            imported_rows: 3,
            error_message: "не показывать",
          }),
        ],
        25,
      ),
    );
    renderWithSWR(<ImportHistory />);

    expect(await screen.findByText("В файле не найдено операций.")).toBeInTheDocument();
    expect(screen.queryByText("не показывать")).not.toBeInTheDocument();
    expect(screen.getByText("Ошибка")).toBeInTheDocument();
    expect(screen.getByText("Импортирован")).toBeInTheDocument();
    expect(api.listImports).toHaveBeenCalledWith({ limit: 20, offset: 0 });

    await user.click(screen.getByRole("button", { name: "Следующая страница" }));
    await waitFor(() =>
      expect(api.listImports).toHaveBeenLastCalledWith({ limit: 20, offset: 20 }),
    );
  });

  it("shows the empty state", async () => {
    api.listImports.mockResolvedValue(page([]));
    renderWithSWR(<ImportHistory />);
    expect(await screen.findByText("Импортов пока нет")).toBeInTheDocument();
  });
});
