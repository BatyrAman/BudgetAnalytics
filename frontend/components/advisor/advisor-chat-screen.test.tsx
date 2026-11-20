import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { askAdvisor, getMe } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { User } from "@/lib/types";
import { AdvisorChatScreen } from "./advisor-chat-screen";
import { makeAnswer } from "./advisor-test-fixtures";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  askAdvisor: vi.fn(),
  getMe: vi.fn(),
}));

const user: User = {
  id: 1,
  full_name: "Тест",
  email: "t@example.com",
  is_active: true,
  default_currency_code: "USD",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

function renderScreen() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AdvisorChatScreen />
    </SWRConfig>,
  );
}

const field = () => screen.getByLabelText("Ваш вопрос");
const submit = () => screen.getByRole("button", { name: "Отправить вопрос" });

// Generous timeout: jsdom renders are slow on a loaded CI/dev machine.
describe("AdvisorChatScreen", () => {
  beforeEach(() => {
    vi.mocked(getMe).mockResolvedValue(user);
    vi.mocked(askAdvisor).mockResolvedValue(makeAnswer());
  });

  it("shows the counter, the PII warning and history note", async () => {
    renderScreen();
    expect(screen.getByText("0 / 500")).toBeInTheDocument();
    expect(screen.getByText("Не указывайте номера карт, ИИН и пароли")).toBeInTheDocument();
    expect(
      screen.getByText("История не сохраняется: каждый вопрос обрабатывается отдельно"),
    ).toBeInTheDocument();
    fireEvent.change(field(), { target: { value: "Привет" } });
    expect(screen.getByText("6 / 500")).toBeInTheDocument();
  });

  it("blocks a 2-character question", async () => {
    renderScreen();
    fireEvent.change(field(), { target: { value: "аб" } });
    await userEvent.click(submit());
    expect(screen.getByRole("alert")).toHaveTextContent("Вопрос должен быть от 3 до 500 символов");
    expect(askAdvisor).not.toHaveBeenCalled();
  });

  it("blocks a 501-character question", async () => {
    renderScreen();
    fireEvent.change(field(), { target: { value: "а".repeat(501) } });
    expect(screen.getByText("501 / 500")).toBeInTheDocument();
    await userEvent.click(submit());
    expect(screen.getByRole("alert")).toHaveTextContent("Вопрос должен быть от 3 до 500 символов");
    expect(askAdvisor).not.toHaveBeenCalled();
  });

  it("sends only the current question with the default currency, never history", async () => {
    vi.mocked(askAdvisor)
      .mockResolvedValueOnce(
        makeAnswer({
          answer: { ...makeAnswer().answer, follow_up_question: "Как увеличить резерв?" },
        }),
      )
      .mockResolvedValueOnce(makeAnswer());
    renderScreen();
    // Let useMe() resolve so the default currency comes from the profile.
    await waitFor(() => expect(getMe).toHaveBeenCalled());
    await act(() => Promise.resolve());
    fireEvent.change(field(), { target: { value: "  Куда уходят деньги?  " } });
    await userEvent.click(submit());
    await screen.findByText("Больше всего уходит на продукты.");
    expect(askAdvisor).toHaveBeenLastCalledWith("Куда уходят деньги?", "USD");

    await userEvent.click(screen.getByRole("button", { name: "Как увеличить резерв?" }));
    await waitFor(() => expect(askAdvisor).toHaveBeenCalledTimes(2));
    expect(askAdvisor).toHaveBeenLastCalledWith("Как увеличить резерв?", "USD");
    for (const call of vi.mocked(askAdvisor).mock.calls) expect(call).toHaveLength(2);
    expect(field()).toHaveValue("");
  });

  it("starts with a suggested question chip", async () => {
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Хватит ли подушки безопасности?" }));
    await waitFor(() =>
      expect(askAdvisor).toHaveBeenCalledWith(
        "Хватит ли подушки безопасности?",
        expect.any(String),
      ),
    );
  });

  it("shows the AI label and the as-of date", async () => {
    renderScreen();
    fireEvent.change(field(), { target: { value: "Вопрос?" } });
    await userEvent.click(submit());
    const card = (await screen.findByText("Больше всего уходит на продукты.")).closest("article")!;
    expect(within(card).getByText("AI")).toBeInTheDocument();
    expect(within(card).getByText("Данные на 31.01.2025")).toBeInTheDocument();
  });

  it.each([
    ["disabled", "AI отключён, ответ подготовлен по правилам"],
    ["limit_reached", "Дневной лимит AI исчерпан — ответ подготовлен по правилам"],
    ["provider_error", "AI временно недоступен — ответ подготовлен по правилам"],
    ["invalid_output", "Ответ AI не прошёл проверку — показан ответ по правилам"],
  ] as const)("shows rules fallback text for %s", async (reason, text) => {
    vi.mocked(askAdvisor).mockResolvedValue(
      makeAnswer({ generated_by: "rules", fallback_reason: reason }),
    );
    renderScreen();
    fireEvent.change(field(), { target: { value: "Вопрос?" } });
    await userEvent.click(submit());
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getByText("Ответ по правилам")).toBeInTheDocument();
  });

  it("shows the advisor rate limit message on 429", async () => {
    vi.mocked(askAdvisor).mockRejectedValue(new ApiError({ status: 429, code: "http_429" }));
    renderScreen();
    fireEvent.change(field(), { target: { value: "Вопрос?" } });
    await userEvent.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Лимит запросов к советнику: 30 в час. Попробуйте позже",
    );
  });

  it("shows a Russian message for other API errors", async () => {
    vi.mocked(askAdvisor).mockRejectedValue(
      new ApiError({ status: 503, code: "backend_unavailable" }),
    );
    renderScreen();
    fireEvent.change(field(), { target: { value: "Вопрос?" } });
    await userEvent.click(submit());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сервер недоступен. Попробуйте позже.",
    );
  });

  it("lists only the facts referenced by evidence", async () => {
    renderScreen();
    fireEvent.change(field(), { target: { value: "Вопрос?" } });
    await userEvent.click(submit());
    const panel = await screen.findByRole("complementary", { name: "Факты последнего ответа" });
    await waitFor(() => expect(within(panel).getAllByTestId("advisor-fact")).toHaveLength(2));
    expect(within(panel).getByText("Расходы за месяц")).toBeInTheDocument();
    expect(within(panel).getByText("120000.00 KZT · 2025-01")).toBeInTheDocument();
    expect(within(panel).getByText("Подушка безопасности")).toBeInTheDocument();
    expect(within(panel).queryByText("Доход за месяц")).not.toBeInTheDocument();
  });

  it("shows the needs-more-data hint", async () => {
    vi.mocked(askAdvisor).mockResolvedValue(
      makeAnswer({ answer: { ...makeAnswer().answer, needs_more_data: true } }),
    );
    renderScreen();
    fireEvent.change(field(), { target: { value: "Вопрос?" } });
    await userEvent.click(submit());
    expect(
      await screen.findByText("Добавьте операции или счета, чтобы ответ был точнее"),
    ).toBeInTheDocument();
  });
});
