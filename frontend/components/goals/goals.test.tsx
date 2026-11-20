import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Goal, User } from "@/lib/types";

import { GoalDetailScreen } from "./goal-detail-screen";
import { GoalsScreen } from "./goals-screen";

vi.mock("@/components/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listGoals: vi.fn(),
  getGoal: vi.fn(),
  createGoal: vi.fn(),
  updateGoal: vi.fn(),
  deleteGoal: vi.fn(),
}));

const mocked = vi.mocked(api);

function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>,
  );
}

const me: User = {
  id: 1,
  full_name: "Тест",
  email: "test@example.com",
  is_active: true,
  default_currency_code: "EUR",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const goal: Goal = {
  id: 5,
  name: "Отпуск",
  currency_code: "KZT",
  target_amount: "500000.00",
  saved_amount: "100000.00",
  target_date: "2027-06-01",
  // Derived values come only from the API — deliberately not consistent with
  // saved/target so a client-side recomputation would be noticed.
  progress_percent: "33.30",
  remaining: "123456.00",
  is_reached: false,
  months_left: 7,
  required_monthly_saving: "17636.57",
};

beforeEach(() => {
  mocked.getMe.mockResolvedValue(me);
  mocked.listGoals.mockResolvedValue([goal]);
  mocked.getGoal.mockResolvedValue(goal);
});

describe("GoalsScreen (G-1, G-3)", () => {
  it("renders derived values from the API only", async () => {
    renderWithSWR(<GoalsScreen />);
    expect(await screen.findByText("Отпуск")).toBeInTheDocument();
    expect(screen.getByText("33,3 %")).toBeInTheDocument();
    expect(screen.getByText("Осталось: 123 456,00 ₸")).toBeInTheDocument();
    expect(screen.getByText("17 636,57 ₸ в месяц")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("creates a goal with string amounts and the profile currency", async () => {
    mocked.createGoal.mockResolvedValue({ ...goal, id: 6, name: "Машина" });
    renderWithSWR(<GoalsScreen />);
    await screen.findByText("Отпуск");
    await userEvent.click(screen.getByRole("button", { name: "Новая цель" }));
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(within(dialog).getByLabelText("Валюта")).toHaveValue("EUR"));
    await userEvent.type(within(dialog).getByLabelText(/Название/), "Машина");
    await userEvent.type(within(dialog).getByLabelText(/Целевая сумма/), "3 000 000");
    await userEvent.clear(within(dialog).getByLabelText("Уже накоплено"));
    await userEvent.type(within(dialog).getByLabelText("Уже накоплено"), "250000,5");
    await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить цель" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mocked.createGoal).toHaveBeenCalledWith({
      name: "Машина",
      target_amount: "3000000",
      saved_amount: "250000.5",
      currency: "EUR",
      target_date: null,
    });
    await waitFor(() => expect(mocked.listGoals).toHaveBeenCalledTimes(2));
  });

  it("shows goal_name_taken at the name field", async () => {
    mocked.createGoal.mockRejectedValue(new ApiError({ status: 409, code: "goal_name_taken" }));
    renderWithSWR(<GoalsScreen />);
    await screen.findByText("Отпуск");
    await userEvent.click(screen.getByRole("button", { name: "Новая цель" }));
    await userEvent.type(screen.getByLabelText(/Название/), "Отпуск");
    await userEvent.type(screen.getByLabelText(/Целевая сумма/), "100");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить цель" }));
    expect(await screen.findByText("Цель с таким названием уже есть.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Название/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    mocked.listGoals.mockResolvedValue([]);
    renderWithSWR(<GoalsScreen />);
    expect(await screen.findByText("Целей пока нет")).toBeInTheDocument();
  });
});

describe("GoalDetailScreen (G-2)", () => {
  it("«Обновить накопления» sends the new total as a string", async () => {
    mocked.updateGoal.mockResolvedValue({ ...goal, saved_amount: "150000.00" });
    renderWithSWR(<GoalDetailScreen id={5} />);
    await userEvent.click(await screen.findByRole("button", { name: "Обновить накопления" }));
    const input = screen.getByLabelText(/Сейчас накоплено/);
    expect(input).toHaveValue("100000.00");
    await userEvent.clear(input);
    await userEvent.type(input, "150 000");
    await userEvent.click(screen.getByRole("button", { name: "Обновить" }));

    await waitFor(() =>
      expect(mocked.updateGoal).toHaveBeenCalledWith(5, { saved_amount: "150000" }),
    );
    await waitFor(() => expect(mocked.getGoal).toHaveBeenCalledTimes(2));
  });

  it("locks the currency when editing", async () => {
    renderWithSWR(<GoalDetailScreen id={5} />);
    await userEvent.click(await screen.findByRole("button", { name: "Изменить" }));
    expect(screen.getByLabelText(/^Валюта/)).toBeDisabled();
    expect(screen.getByLabelText(/^Валюта/)).toHaveValue("KZT");
    expect(screen.getByText("Валюту цели нельзя изменить")).toBeInTheDocument();
  });

  it("shows goal_not_found as a Russian error", async () => {
    mocked.getGoal.mockRejectedValue(new ApiError({ status: 404, code: "goal_not_found" }));
    renderWithSWR(<GoalDetailScreen id={99} />);
    expect(await screen.findByText("Цель не найдена.")).toBeInTheDocument();
  });
});
