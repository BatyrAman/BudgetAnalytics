import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";

import { TransactionForm } from "./transaction-form";
import { account, apiError, banks, categories, renderWithSWR, transaction } from "./test-utils";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listCategories: vi.fn(),
  listAccounts: vi.fn(),
  listBanks: vi.fn(),
  createTransaction: vi.fn(),
  updateTransaction: vi.fn(),
}));

const api = vi.mocked(client);

beforeEach(() => {
  api.getMe.mockResolvedValue({
    id: 1,
    full_name: "Тест",
    email: "t@example.com",
    is_active: true,
    default_currency_code: "USD",
    created_at: "",
    updated_at: "",
  });
  api.listCategories.mockResolvedValue(categories);
  api.listAccounts.mockResolvedValue([
    account({ id: 10, name: "Евро-карта", currency_code: "EUR" }),
    account({ id: 11, name: "Старая карта", is_archived: true }),
  ]);
  api.listBanks.mockResolvedValue(banks);
});

function renderForm(props: Partial<Parameters<typeof TransactionForm>[0]> = {}) {
  const onClose = vi.fn();
  const onSaved = vi.fn();
  renderWithSWR(<TransactionForm onClose={onClose} onSaved={onSaved} {...props} />);
  return { onClose, onSaved };
}

async function ready() {
  await screen.findByRole("option", { name: "Продукты" });
}

describe("TransactionForm (T-3)", () => {
  it("sends the amount as a string, the date with the time-zone offset and the default currency", async () => {
    const user = userEvent.setup();
    api.createTransaction.mockResolvedValue(transaction());
    const { onSaved } = renderForm();
    await ready();
    await waitFor(() => expect(screen.getByLabelText(/^Валюта/)).toHaveValue("USD"));

    await user.type(screen.getByLabelText(/^Сумма/), "12 500,5");
    expect(screen.getByLabelText(/^Сумма/)).toHaveValue("12500.5");
    fireEvent.change(screen.getByLabelText(/Дата и время/), {
      target: { value: "2026-11-19T10:15" },
    });
    await user.selectOptions(screen.getByLabelText(/^Категория/), "1");
    await user.type(screen.getByLabelText(/^Описание/), "  Кофе  ");
    await user.click(screen.getByRole("button", { name: "Добавить операцию" }));

    await waitFor(() =>
      expect(api.createTransaction).toHaveBeenCalledWith({
        amount: "12500.5",
        transaction_type: "expense",
        transaction_date: "2026-11-19T10:15:00+05:00",
        category_id: 1,
        description: "Кофе",
        account_id: null,
        bank_id: null,
        currency: "USD",
      }),
    );
    expect(typeof api.createTransaction.mock.calls[0][0].amount).toBe("string");
    expect(onSaved).toHaveBeenCalled();
  });

  it("locks the currency to the chosen account and hides archived accounts", async () => {
    const user = userEvent.setup();
    api.createTransaction.mockResolvedValue(transaction());
    renderForm();
    await ready();
    await screen.findByRole("option", { name: /Евро-карта/ });
    expect(screen.queryByRole("option", { name: /Старая карта/ })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/^Счёт/), "10");
    expect(screen.getByLabelText(/^Валюта/)).toBeDisabled();
    expect(screen.getByLabelText(/^Валюта/)).toHaveValue("EUR");

    await user.type(screen.getByLabelText(/^Сумма/), "100");
    await user.selectOptions(screen.getByLabelText(/^Категория/), "3");
    await user.click(screen.getByRole("button", { name: "Добавить операцию" }));
    await waitFor(() =>
      expect(api.createTransaction).toHaveBeenCalledWith(
        expect.objectContaining({ account_id: 10, currency: "EUR", amount: "100", category_id: 3 }),
      ),
    );
  });

  it("maps category_kind_mismatch from the server to the category field", async () => {
    const user = userEvent.setup();
    api.createTransaction.mockRejectedValue(apiError(400, "category_kind_mismatch"));
    renderForm();
    await ready();
    await user.type(screen.getByLabelText(/^Сумма/), "50");
    await user.selectOptions(screen.getByLabelText(/^Категория/), "1");
    await user.click(screen.getByRole("button", { name: "Добавить операцию" }));

    const message = await screen.findByText("Категория не подходит для этого типа операции.");
    const select = screen.getByLabelText(/^Категория/);
    expect(select).toHaveAttribute("aria-invalid", "true");
    expect(select.getAttribute("aria-describedby")).toBe(message.id);
  });

  it("shows 422 field errors next to the fields", async () => {
    const user = userEvent.setup();
    api.createTransaction.mockRejectedValue(
      apiError(422, "validation_error", [{ field: "amount", message: "Слишком большое число." }]),
    );
    renderForm();
    await ready();
    await user.type(screen.getByLabelText(/^Сумма/), "50");
    await user.selectOptions(screen.getByLabelText(/^Категория/), "1");
    await user.click(screen.getByRole("button", { name: "Добавить операцию" }));
    expect(await screen.findByText("Слишком большое число.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Сумма/)).toHaveAttribute("aria-invalid", "true");
  });

  it("validates on the client before calling the API", async () => {
    const user = userEvent.setup();
    renderForm();
    await ready();
    await user.type(screen.getByLabelText(/^Сумма/), "0");
    await user.click(screen.getByRole("button", { name: "Добавить операцию" }));
    expect(screen.getByText("Сумма должна быть больше нуля.")).toBeInTheDocument();
    expect(screen.getByText("Выберите категорию.")).toBeInTheDocument();
    expect(api.createTransaction).not.toHaveBeenCalled();
  });

  it("resets an incompatible category when the type changes and keeps an 'any' category", async () => {
    const user = userEvent.setup();
    renderForm();
    await ready();
    const category = screen.getByLabelText(/^Категория/);

    await user.selectOptions(category, "1"); // expense category
    await user.click(screen.getByRole("button", { name: "Доход" }));
    expect(category).toHaveValue("");
    expect(screen.queryByRole("option", { name: "Продукты" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Зарплата" })).toBeInTheDocument();

    await user.selectOptions(category, "3"); // "any"
    await user.click(screen.getByRole("button", { name: "Возврат" }));
    expect(category).toHaveValue("3");
  });

  it("sends PATCH for an existing transaction", async () => {
    const user = userEvent.setup();
    api.updateTransaction.mockResolvedValue(transaction({ amount: "99.90" }));
    renderForm({ transaction: transaction({ account_id: null, currency_code: "KZT" }) });
    await ready();
    const amount = screen.getByLabelText(/^Сумма/);
    await user.clear(amount);
    await user.type(amount, "99,9");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(api.updateTransaction).toHaveBeenCalledWith(
        100,
        expect.objectContaining({
          amount: "99.9",
          currency: "KZT",
          transaction_date: "2026-11-10T14:30:00+05:00",
        }),
      ),
    );
  });

  it("closes immediately when nothing changed", async () => {
    const user = userEvent.setup();
    const { onClose } = renderForm();
    await ready();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("confirms discarding a dirty form", async () => {
    const user = userEvent.setup();
    const { onClose } = renderForm();
    await ready();
    await user.type(screen.getByLabelText(/^Сумма/), "10");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
