import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getAdvisorReport, getMe } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { AdvisorReportScreen } from "./advisor-report-screen";
import { makeReport } from "./advisor-test-fixtures";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getAdvisorReport: vi.fn(),
  getMe: vi.fn(),
}));

function renderScreen() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AdvisorReportScreen />
    </SWRConfig>,
  );
}

const generate = () => screen.getByRole("button", { name: /Сформировать отчёт/ });

// Generous timeout: jsdom renders are slow on a loaded CI/dev machine.
describe("AdvisorReportScreen", () => {
  beforeEach(() => {
    vi.mocked(getMe).mockRejectedValue(new ApiError({ status: 500, code: "http_500" }));
    vi.mocked(getAdvisorReport).mockResolvedValue(makeReport());
  });

  it("does not request a report until the button is pressed", () => {
    renderScreen();
    expect(getAdvisorReport).not.toHaveBeenCalled();
    expect(screen.getByText("Отчёта пока нет")).toBeInTheDocument();
    expect(
      screen.getByText("Отчёт не сохраняется; повторное формирование расходует лимит"),
    ).toBeInTheDocument();
  });

  it("renders all report sections, priorities and the investment marker", async () => {
    renderScreen();
    await userEvent.click(generate());
    expect(await screen.findByText("Расходы стабильны.")).toBeInTheDocument();
    // Currency falls back to KZT while the profile is unavailable.
    expect(getAdvisorReport).toHaveBeenCalledWith("KZT");

    for (const title of [
      "Наблюдения",
      "Рекомендации",
      "Риски",
      "Допущения",
      "Каких данных не хватает",
      "Факты F1–F3",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(screen.getByText("Продукты лидируют")).toBeInTheDocument();
    expect(screen.getByText("Нет данных о кредитах")).toBeInTheDocument();
    expect(screen.getByText("Доход стабилен")).toBeInTheDocument();
    expect(screen.getByText("Расчёты носят информационный характер.")).toBeInTheDocument();

    const cards = screen.getAllByTestId("advisor-recommendation");
    expect(within(cards[0]).getByText("Приоритет: Высокий")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Приоритет: Средний")).toBeInTheDocument();
    expect(within(cards[2]).getByText("Приоритет: Низкий")).toBeInTheDocument();
    expect(within(cards[2]).getByText("Касается инвестиций")).toBeInTheDocument();
    expect(within(cards[0]).queryByText("Касается инвестиций")).not.toBeInTheDocument();
    expect(screen.getByText("Серьёзность: Высокий")).toBeInTheDocument();
  });

  it("shows the rules fallback reason for a report", async () => {
    vi.mocked(getAdvisorReport).mockResolvedValue(
      makeReport({ generated_by: "rules", fallback_reason: "limit_reached" }),
    );
    renderScreen();
    await userEvent.click(generate());
    expect(
      await screen.findByText("Дневной лимит AI исчерпан — ответ подготовлен по правилам"),
    ).toBeInTheDocument();
  });

  it("shows the advisor limit message on 429", async () => {
    vi.mocked(getAdvisorReport).mockRejectedValue(new ApiError({ status: 429, code: "http_429" }));
    renderScreen();
    await userEvent.click(generate());
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Лимит запросов к советнику: 30 в час. Попробуйте позже",
      ),
    );
  });
});
