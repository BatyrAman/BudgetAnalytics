import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { NotificationsScreen } from "./notifications-screen";

// Generous timeout: jsdom renders are slow on a loaded CI/dev machine.
describe("NotificationsScreen", () => {
  it("shows the backend banner, badge and empty state by default", () => {
    render(<NotificationsScreen />);
    expect(
      screen.getByText(
        "Уведомления пока не поддерживаются backend — экран показывает планируемый дизайн",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Требует backend").length).toBeGreaterThan(0);
    expect(screen.getByText("Уведомлений пока нет")).toBeInTheDocument();
    expect(screen.queryByText("Пример")).not.toBeInTheDocument();
  });

  it("has no enabled bulk actions", () => {
    render(<NotificationsScreen />);
    const markAll = screen.getByRole("button", { name: /Отметить всё прочитанным/ });
    expect(markAll).toBeDisabled();
    expect(markAll.parentElement).toHaveAttribute("title", "Требует backend");
  });

  it("shows labelled examples in development and opens a sheet", async () => {
    render(<NotificationsScreen />);
    await userEvent.click(screen.getByRole("switch", { name: /Демо: макет списка/ }));
    expect(screen.getAllByText("Пример")).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: /Цель достигнута/ }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Отпуск в Турции");
    expect(screen.getByRole("link", { name: /Открыть цели/ })).toHaveAttribute("href", "/goals");
    await userEvent.click(screen.getByRole("button", { name: "Закрыть подробности" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
