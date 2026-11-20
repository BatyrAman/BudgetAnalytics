import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./confirm-dialog";

function setup(props: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      title="Удалить операцию?"
      description="Действие нельзя отменить."
      confirmLabel="Удалить"
      busyLabel="Удаление…"
      danger
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...props}
    />,
  );
  return { onConfirm, onCancel };
}

describe("ConfirmDialog", () => {
  it("is an accessible alertdialog with focus on cancel", () => {
    setup();
    const dialog = screen.getByRole("alertdialog", { name: "Удалить операцию?" });
    expect(dialog).toHaveAccessibleDescription("Действие нельзя отменить.");
    expect(screen.getByRole("button", { name: "Отмена" })).toHaveFocus();
  });

  it("confirms, cancels by Escape anywhere and by the backdrop", () => {
    const { onConfirm, onCancel } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.mouseDown(screen.getByRole("presentation"));
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("blocks every way out while the action is running", () => {
    const { onConfirm, onCancel } = setup({ busy: true });
    expect(screen.getByRole("button", { name: "Удаление…" })).toBeDisabled();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.mouseDown(screen.getByRole("presentation"));
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("shows an API error and keeps ids unique for two dialogs", () => {
    setup({ error: "Сервер недоступен. Попробуйте позже." });
    setup({ title: "Второй" });
    expect(screen.getByRole("alert")).toHaveTextContent("Сервер недоступен");
    const ids = screen.getAllByRole("alertdialog").map((d) => d.getAttribute("aria-labelledby"));
    expect(new Set(ids).size).toBe(2);
  });
});
