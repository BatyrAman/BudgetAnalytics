import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Deposit, DepositCalculation, Maturity, Overview, User } from "@/lib/types";

import { DepositCalculator } from "./deposit-calculator";
import { DepositDetail } from "./deposit-detail";
import { DepositsList } from "./deposit-list";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listBanks: vi.fn(),
  listDeposits: vi.fn(),
  getDeposit: vi.fn(),
  getOverview: vi.fn(),
  calculateDeposit: vi.fn(),
  createDeposit: vi.fn(),
  updateDeposit: vi.fn(),
  deleteDeposit: vi.fn(),
}));

const api = vi.mocked(client);
// Form flows type character by character with user-event; allow for slow CI machines.
const NBSP = "\u00a0";

const BACKEND_ASSUMPTIONS = [
  "Nominal rate, ACT/365 day count; interest rounded once to the currency minor unit (half up).",
  "Capitalization on monthly/quarterly/annual anniversaries of the start date; simple interest for the remaining days.",
  "No top-ups, withdrawals, fees, taxes or early-termination rules are modelled; the bank's figures may differ.",
];

const user: User = {
  id: 1,
  full_name: "Тест",
  email: "t@example.com",
  is_active: true,
  default_currency_code: "KZT",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
// Backend control example: 1 000 000 at 16 %, monthly capitalization, 12 months.
const maturity: Maturity = {
  term_days: 365,
  capitalization_periods: 12,
  stub_days: 0,
  interest: "172270.80",
  maturity_amount: "1172270.80",
  effective_annual_rate: "17.2271",
  assumptions: BACKEND_ASSUMPTIONS,
};
const calculation: DepositCalculation = {
  principal: "1000000.00",
  currency_code: "KZT",
  interest_rate: "16.00",
  capitalization: "monthly",
  start_date: "2026-11-19",
  maturity_date: "2027-11-19",
  maturity,
};
const deposit: Deposit = {
  id: 42,
  bank_id: 3,
  principal: "1000000.00",
  currency_code: "KZT",
  interest_rate: "16.00",
  effective_rate: "17.2000",
  capitalization: "monthly",
  start_date: "2026-11-19",
  end_date: "2027-11-19",
  maturity,
  data_issue: null,
};
// A legacy row stored before the term bounds: no estimate, only a stable code.
const legacyDeposit: Deposit = {
  ...deposit,
  id: 43,
  start_date: "2025-01-01",
  end_date: "2100-01-01",
  maturity: null,
  data_issue: "term_too_long",
};
const overview = {
  generated_at: "2026-11-19T05:00:00Z",
  timezone: "Asia/Almaty",
  currency_code: "KZT",
  month: "2026-11",
  indicators: {
    deposits_principal: "1000000.00",
    deposits_expected_interest: "172270.80",
  },
} as Overview;

function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-19T05:00:00Z"));
  api.getMe.mockResolvedValue(user);
  api.listBanks.mockResolvedValue([
    { id: 3, name: "Халык Банк", logo: null },
    { id: 4, name: "Каспи Банк", logo: null },
  ]);
  api.listDeposits.mockResolvedValue({ items: [deposit], total: 1, limit: 10, offset: 0 });
  api.getDeposit.mockResolvedValue(deposit);
  api.getOverview.mockResolvedValue(overview);
  api.calculateDeposit.mockResolvedValue(calculation);
  api.createDeposit.mockResolvedValue(deposit);
  api.updateDeposit.mockResolvedValue(deposit);
  api.deleteDeposit.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
  vi.mocked(useRouter().push).mockClear();
});

describe("DepositCalculator (DP-3)", () => {
  it("keeps the range hint out of the field name and exposes it as the description", () => {
    renderWithSWR(<DepositCalculator />);
    const term = screen.getByRole("textbox", { name: "Срок в месяцах *" });
    expect(term).toHaveAccessibleDescription("От 1 до 600");
  });

  it("posts strings with term_months only and renders the API result", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1 000 000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "16");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "12");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));

    await waitFor(() => expect(api.calculateDeposit).toHaveBeenCalledTimes(1));
    const input = api.calculateDeposit.mock.calls[0][0];
    expect(input).toEqual({
      principal: "1000000",
      currency: "KZT",
      interest_rate: "16",
      capitalization: "monthly",
      start_date: "2026-11-19",
      term_months: 12,
    });
    expect(input).not.toHaveProperty("end_date");

    // Testing Library collapses NBSP into spaces when matching; check the raw text too.
    const interest = await screen.findAllByText("172 270,80 ₸");
    expect(interest[0].textContent).toBe(`172${NBSP}270,80${NBSP}₸`);
    expect(screen.getAllByText(`1 172 270,80 ₸`)).not.toHaveLength(0);
    expect(screen.getByText(`17,2271 %`)).toBeInTheDocument();
    expect(screen.queryByText(/Демо/)).not.toBeInTheDocument();
    expect(screen.getByText(/Номинальная ставка, база ACT\/365/)).toBeInTheDocument();
  });

  it("sends end_date only in date mode", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "500000,50");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "14,5");
    await u.click(screen.getByRole("button", { name: "Дата окончания" }));
    await u.type(screen.getByLabelText(/^Дата окончания/), "2027-05-19");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));

    await waitFor(() => expect(api.calculateDeposit).toHaveBeenCalledTimes(1));
    const input = api.calculateDeposit.mock.calls[0][0];
    expect(input).toMatchObject({
      principal: "500000.50",
      interest_rate: "14.5",
      end_date: "2027-05-19",
    });
    expect(input).not.toHaveProperty("term_months");
  });

  it("validates principal, rate and term before calling the API", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "0");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "101");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "601");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));

    expect(await screen.findByText("Сумма должна быть больше нуля.")).toBeInTheDocument();
    expect(
      screen.getByText("Ставка — от 0 до 100 %, не больше 2 знаков после запятой."),
    ).toBeInTheDocument();
    expect(screen.getByText("Срок — целое число месяцев от 1 до 600.")).toBeInTheDocument();

    await u.click(screen.getByRole("button", { name: "Дата окончания" }));
    // `min` blocks typing an earlier date, so set it directly (e.g. a pasted value).
    fireEvent.change(screen.getByLabelText(/^Дата окончания/), {
      target: { value: "2026-11-01" },
    });
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(
      await screen.findByText("Дата окончания должна быть позже даты начала."),
    ).toBeInTheDocument();
    expect(api.calculateDeposit).not.toHaveBeenCalled();
  });

  it("maps unknown_currency and field errors from the API", async () => {
    api.calculateDeposit.mockRejectedValueOnce(
      new ApiError({ status: 400, code: "unknown_currency" }),
    );
    api.calculateDeposit.mockRejectedValueOnce(
      new ApiError({
        status: 422,
        code: "validation_error",
        fieldErrors: [{ field: "principal", message: "Слишком большое число." }],
      }),
    );
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "10");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "6");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(await screen.findByText("Эта валюта не поддерживается.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Валюта/)).toHaveAttribute("aria-invalid", "true");

    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(await screen.findByText("Слишком большое число.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Сумма/)).toHaveAttribute("aria-invalid", "true");
  });

  it("rejects a 601-month term in date mode on the end date field", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "10");
    await u.click(screen.getByRole("button", { name: "Дата окончания" }));
    // Start defaults to today (2026-11-19): 600 months end on 2076-11-19.
    fireEvent.change(screen.getByLabelText(/^Дата окончания/), {
      target: { value: "2076-11-20" },
    });
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(
      await screen.findByText("Срок вклада — не больше 600 месяцев (50 лет)."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^Дата окончания/)).toHaveAttribute("aria-invalid", "true");
    expect(api.calculateDeposit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/^Дата окончания/), {
      target: { value: "2076-11-19" },
    });
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    await waitFor(() => expect(api.calculateDeposit).toHaveBeenCalledTimes(1));
  });

  it("rejects a 601-month term in months mode on the term field", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "10");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "601");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(await screen.findByText("Срок — целое число месяцев от 1 до 600.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Срок в месяцах/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText("Проверьте правильность заполнения полей.")).not.toBeInTheDocument();
    expect(api.calculateDeposit).not.toHaveBeenCalled();

    await u.clear(screen.getByLabelText(/^Срок в месяцах/));
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "600");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    await waitFor(() => expect(api.calculateDeposit).toHaveBeenCalledTimes(1));
    expect(api.calculateDeposit.mock.calls[0][0]).toMatchObject({ term_months: 600 });
  });

  it("checks date bounds and the computed maturity in months mode", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "10");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "12");
    fireEvent.change(screen.getByLabelText(/^Дата начала/), { target: { value: "1899-12-31" } });
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(await screen.findByText("Дата не может быть раньше 01.01.1900.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Дата начала/)).toHaveAttribute("aria-invalid", "true");

    fireEvent.change(screen.getByLabelText(/^Дата начала/), { target: { value: "2200-06-01" } });
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(
      await screen.findByText("Дата окончания вклада не может быть позже 31.12.2200."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^Срок в месяцах/)).toHaveAttribute("aria-invalid", "true");
    expect(api.calculateDeposit).not.toHaveBeenCalled();
  });

  it("shows a backend error without a field (loc: []) on the term field", async () => {
    api.calculateDeposit.mockRejectedValueOnce(
      new ApiError({
        status: 422,
        code: "validation_error",
        fieldErrors: [{ field: "_", message: "Некорректное значение.", type: "value_error" }],
      }),
    );
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "10");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "12");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    expect(await screen.findByText(/срок — не больше 600 месяцев/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Срок в месяцах/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByText("Проверьте правильность заполнения полей.")).not.toBeInTheDocument();
  });

  it("saves the calculation as a deposit with maturity_date as end_date; bank is required", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositCalculator />);
    await u.type(screen.getByLabelText(/^Сумма/), "1000000");
    await u.type(screen.getByLabelText(/^Номинальная ставка/), "16");
    await u.type(screen.getByLabelText(/^Срок в месяцах/), "12");
    await u.click(screen.getByRole("button", { name: "Рассчитать" }));
    await u.click(await screen.findByRole("button", { name: "Сохранить как депозит" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(/^Дата окончания/)).toHaveValue("2027-11-19");
    expect(within(dialog).getByLabelText(/^Сумма/)).toHaveValue("1000000.00");

    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(await within(dialog).findByText("Выберите банк.")).toBeInTheDocument();
    expect(api.createDeposit).not.toHaveBeenCalled();

    await within(dialog).findByRole("option", { name: "Халык Банк" });
    await u.selectOptions(within(dialog).getByLabelText(/^Банк/), "3");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    await waitFor(() =>
      expect(api.createDeposit).toHaveBeenCalledWith({
        bank_id: 3,
        principal: "1000000.00",
        currency: "KZT",
        interest_rate: "16.00",
        capitalization: "monthly",
        start_date: "2026-11-19",
        end_date: "2027-11-19",
      }),
    );
    await waitFor(() => expect(useRouter().push).toHaveBeenCalledWith("/deposits/42"));
  });
});

describe("DepositsList (DP-1) and form", () => {
  it("shows bank names and totals from the overview", async () => {
    renderWithSWR(<DepositsList />);
    expect(await screen.findByRole("heading", { name: "Халык Банк" })).toBeInTheDocument();
    const totals = await screen.findByRole("region", { name: "Итоги по вкладам" });
    expect(within(totals).getByText(`1 000 000 ₸`)).toBeInTheDocument();
    expect(within(totals).getByText(`172 270,80 ₸`)).toBeInTheDocument();
    expect(api.getOverview).toHaveBeenCalledWith("KZT");
    expect(api.listDeposits).toHaveBeenCalledWith({ limit: 10, offset: 0 });
  });

  it("shows the empty state", async () => {
    api.listDeposits.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
    renderWithSWR(<DepositsList />);
    expect(await screen.findByText("Депозитов пока нет")).toBeInTheDocument();
  });

  it("creates a deposit with string amounts and revalidates the list", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositsList />);
    await screen.findByRole("heading", { name: "Халык Банк" });
    expect(api.listDeposits).toHaveBeenCalledTimes(1);
    await u.click(screen.getAllByRole("button", { name: "Добавить депозит" })[0]);
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByRole("option", { name: "Каспи Банк" });
    await u.selectOptions(within(dialog).getByLabelText(/^Банк/), "4");
    await u.type(within(dialog).getByLabelText(/^Сумма/), "250 000,5");
    await u.type(within(dialog).getByLabelText(/^Номинальная ставка/), "15");
    await u.type(within(dialog).getByLabelText(/^ГЭСВ/), "16,0754");
    await u.type(within(dialog).getByLabelText(/^Дата окончания/), "2027-11-19");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));

    await waitFor(() =>
      expect(api.createDeposit).toHaveBeenCalledWith({
        bank_id: 4,
        principal: "250000.5",
        currency: "KZT",
        interest_rate: "15",
        effective_rate: "16.0754",
        capitalization: "monthly",
        start_date: "2026-11-19",
        end_date: "2027-11-19",
      }),
    );
    await waitFor(() => expect(api.listDeposits).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("validates the effective rate range and maps bank_not_found to the bank field", async () => {
    api.createDeposit.mockRejectedValueOnce(new ApiError({ status: 400, code: "bank_not_found" }));
    const u = userEvent.setup();
    renderWithSWR(<DepositsList />);
    await u.click(screen.getAllByRole("button", { name: "Добавить депозит" })[0]);
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByRole("option", { name: "Каспи Банк" });
    await u.selectOptions(within(dialog).getByLabelText(/^Банк/), "4");
    await u.type(within(dialog).getByLabelText(/^Сумма/), "1000");
    await u.type(within(dialog).getByLabelText(/^Номинальная ставка/), "10");
    await u.type(within(dialog).getByLabelText(/^ГЭСВ/), "1000.5");
    await u.type(within(dialog).getByLabelText(/^Дата окончания/), "2027-01-01");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(
      await within(dialog).findByText("ГЭСВ — от 0 до 1000 %, не больше 4 знаков после запятой."),
    ).toBeInTheDocument();
    expect(api.createDeposit).not.toHaveBeenCalled();

    await u.clear(within(dialog).getByLabelText(/^ГЭСВ/));
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(
      await within(dialog).findByText("Банк не найден. Обновите список и выберите снова."),
    ).toBeInTheDocument();
    expect(api.createDeposit.mock.calls[0][0]).not.toHaveProperty("effective_rate");
  });

  it("shows a legacy deposit with data_issue without any estimate", async () => {
    api.listDeposits.mockResolvedValue({
      items: [deposit, legacyDeposit],
      total: 2,
      limit: 10,
      offset: 0,
    });
    renderWithSWR(<DepositsList />);
    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("Расчёт недоступен: Срок больше 600 месяцев (50 лет).");
    expect(notice).toHaveTextContent("не учитывается в итогах");
    // Only the valid deposit shows estimate lines.
    expect(screen.getAllByText(/Доход к концу срока/)).toHaveLength(1);
  });

  it.each([
    ["term_too_long", "Срок вклада не может превышать 600 месяцев (50 лет)."],
    ["date_out_of_range", "Даты вклада должны быть в диапазоне 01.01.1900 — 31.12.2200."],
    ["invalid_date_range", "Дата окончания должна быть позже даты начала."],
  ])("maps %s from the API to the end date field", async (code, message) => {
    api.updateDeposit.mockRejectedValueOnce(new ApiError({ status: 422, code }));
    const u = userEvent.setup();
    renderWithSWR(<DepositsList />);
    await u.click(await screen.findByRole("button", { name: "Изменить депозит Халык Банк" }));
    const dialog = screen.getByRole("dialog");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(await within(dialog).findByText(message)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Дата окончания/)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  async function openCreateForm(u: ReturnType<typeof userEvent.setup>) {
    renderWithSWR(<DepositsList />);
    await u.click(screen.getAllByRole("button", { name: "Добавить депозит" })[0]);
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByRole("option", { name: "Каспи Банк" });
    await u.selectOptions(within(dialog).getByLabelText(/^Банк/), "4");
    await u.type(within(dialog).getByLabelText(/^Сумма/), "1000");
    await u.type(within(dialog).getByLabelText(/^Номинальная ставка/), "10");
    return dialog;
  }

  it("rejects a 601-month term on the end date field before calling the API", async () => {
    const u = userEvent.setup();
    const dialog = await openCreateForm(u);
    // Start defaults to today (2026-11-19): 600 months end on 2076-11-19.
    fireEvent.change(within(dialog).getByLabelText(/^Дата окончания/), {
      target: { value: "2076-11-20" },
    });
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(
      await within(dialog).findByText("Срок вклада — не больше 600 месяцев (50 лет)."),
    ).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Дата окончания/)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(api.createDeposit).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText(/^Дата окончания/), {
      target: { value: "2076-11-19" },
    });
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    await waitFor(() => expect(api.createDeposit).toHaveBeenCalledTimes(1));
  });

  it.each([
    ["Дата начала", "1899-12-31", "Дата не может быть раньше 01.01.1900."],
    ["Дата окончания", "2201-01-01", "Дата не может быть позже 31.12.2200."],
  ])("validates the %s bound (%s) on the client", async (label, value, message) => {
    const u = userEvent.setup();
    const dialog = await openCreateForm(u);
    fireEvent.change(within(dialog).getByLabelText(new RegExp(`^${label}`)), {
      target: { value },
    });
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(await within(dialog).findByText(message)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(new RegExp(`^${label}`))).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(api.createDeposit).not.toHaveBeenCalled();
  });

  it("maps backend date-bound and field-less (loc: []) errors to the date fields", async () => {
    api.createDeposit.mockRejectedValueOnce(
      new ApiError({
        status: 422,
        code: "validation_error",
        fieldErrors: [
          {
            field: "start_date",
            message: "Значение не может быть отрицательным.",
            type: "greater_than_equal",
          },
          { field: "end_date", message: "Значение слишком большое.", type: "less_than_equal" },
        ],
      }),
    );
    api.createDeposit.mockRejectedValueOnce(
      new ApiError({
        status: 422,
        code: "validation_error",
        fieldErrors: [{ field: "_", message: "Некорректное значение.", type: "value_error" }],
      }),
    );
    const u = userEvent.setup();
    const dialog = await openCreateForm(u);
    await u.type(within(dialog).getByLabelText(/^Дата окончания/), "2027-11-19");
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(
      await within(dialog).findByText("Дата не может быть раньше 01.01.1900."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Дата не может быть позже 31.12.2200.")).toBeInTheDocument();
    expect(
      within(dialog).queryByText("Значение не может быть отрицательным."),
    ).not.toBeInTheDocument();

    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    expect(await within(dialog).findByText(/срок — не больше 600 месяцев/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Дата окончания/)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(
      within(dialog).queryByText("Проверьте правильность заполнения полей."),
    ).not.toBeInTheDocument();
  });

  it("updates an existing deposit without currency and clears ГЭСВ with null", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositsList />);
    await u.click(await screen.findByRole("button", { name: "Изменить депозит Халык Банк" }));
    const dialog = screen.getByRole("dialog");
    await u.clear(within(dialog).getByLabelText(/^ГЭСВ/));
    await u.click(within(dialog).getByRole("button", { name: "Сохранить депозит" }));
    await waitFor(() =>
      expect(api.updateDeposit).toHaveBeenCalledWith(42, {
        bank_id: 3,
        principal: "1000000.00",
        interest_rate: "16.00",
        effective_rate: null,
        capitalization: "monthly",
        start_date: "2026-11-19",
        end_date: "2027-11-19",
      }),
    );
  });
});

describe("DepositDetail (DP-2)", () => {
  it("shows three distinct rate labels and translated assumptions", async () => {
    renderWithSWR(<DepositDetail id={42} />);
    expect(await screen.findByText("Номинальная ставка")).toBeInTheDocument();
    expect(screen.getByText("ГЭСВ (по данным банка)")).toBeInTheDocument();
    expect(screen.getByText("Эффективная годовая ставка (расчёт)")).toBeInTheDocument();
    expect(screen.getByText(`17,2000 %`)).toBeInTheDocument();
    expect(screen.getByText(`17,2271 %`)).toBeInTheDocument();
    expect(screen.getByText(/проценты округляются один раз/)).toBeInTheDocument();
    expect(screen.getByText(/на оставшиеся дни — простые проценты/)).toBeInTheDocument();
    expect(screen.getByText(/расчёт банка может отличаться\.$/)).toBeInTheDocument();
    expect(screen.queryByText(/Nominal rate/)).not.toBeInTheDocument();
    expect(screen.queryByText("Допущения backend")).not.toBeInTheDocument();
    expect(api.getDeposit).toHaveBeenCalledWith(42);
  });

  it("shows unknown backend assumptions as-is under a caption", async () => {
    api.getDeposit.mockResolvedValue({
      ...deposit,
      maturity: { ...maturity, assumptions: [...BACKEND_ASSUMPTIONS, "Some new assumption."] },
    });
    renderWithSWR(<DepositDetail id={42} />);
    expect(await screen.findByText("Допущения backend")).toBeInTheDocument();
    expect(screen.getByText("Some new assumption.")).toBeInTheDocument();
  });

  it("shows a data_issue notice instead of the estimate", async () => {
    api.getDeposit.mockResolvedValue({ ...legacyDeposit, data_issue: "date_out_of_range" });
    renderWithSWR(<DepositDetail id={43} />);
    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("Даты вне допустимого диапазона 01.01.1900 — 31.12.2200.");
    expect(screen.queryByText("Эффективная годовая ставка (расчёт)")).not.toBeInTheDocument();
    expect(screen.queryByText(/проценты округляются один раз/)).not.toBeInTheDocument();
  });

  it("shows deposit_not_found as a Russian error", async () => {
    api.getDeposit.mockRejectedValue(new ApiError({ status: 404, code: "deposit_not_found" }));
    renderWithSWR(<DepositDetail id={42} />);
    expect(await screen.findByText("Депозит не найден.")).toBeInTheDocument();
  });

  it("deletes the deposit and returns to the list", async () => {
    const u = userEvent.setup();
    renderWithSWR(<DepositDetail id={42} />);
    await u.click(await screen.findByRole("button", { name: "Удалить" }));
    const dialog = screen.getByRole("alertdialog");
    await u.click(within(dialog).getByRole("button", { name: "Удалить" }));
    await waitFor(() => expect(api.deleteDeposit).toHaveBeenCalledWith(42));
    await waitFor(() => expect(useRouter().push).toHaveBeenCalledWith("/deposits"));
  });
});
