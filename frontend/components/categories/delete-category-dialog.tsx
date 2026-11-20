"use client";

import { useState } from "react";

import { deleteCategory } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import type { Category } from "@/lib/types";

type State = { step: "confirm" | "in-use"; busy: boolean; error: string };

/**
 * Delete confirmation. The backend decides whether the category is in use
 * (409 `category_in_use`); no client-side pre-check is made.
 */
export function DeleteCategoryDialog({
  category,
  onClose,
  onDeleted,
}: {
  category: Category;
  onClose: () => void;
  onDeleted: () => Promise<unknown> | void;
}) {
  const [state, setState] = useState<State>({ step: "confirm", busy: false, error: "" });

  async function confirm() {
    setState({ step: "confirm", busy: true, error: "" });
    try {
      await deleteCategory(category.id);
      await onDeleted();
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.code === "category_in_use") {
        setState({ step: "in-use", busy: false, error: "" });
      } else {
        setState({ step: "confirm", busy: false, error: toUserMessage(error) });
      }
    }
  }

  if (state.step === "in-use") {
    return (
      <div className="overlay-backdrop">
        <section
          className="demo-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="category-in-use-title"
          aria-describedby="category-in-use-text"
        >
          <h2 id="category-in-use-title">Удалить нельзя</h2>
          <p id="category-in-use-text">
            Категория «{category.name}» используется в операциях или бюджетах. Сначала перенесите
            операции в другую категорию или удалите связанные бюджеты.
          </p>
          <div className="dialog-actions">
            <button type="button" className="button primary" onClick={onClose} autoFocus>
              Понятно
            </button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="overlay-backdrop">
      <section
        className="demo-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-category-title"
      >
        <h2 id="delete-category-title">Удалить категорию «{category.name}»?</h2>
        {state.error && (
          <p className="form-error" role="alert">
            {state.error}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="button secondary" onClick={onClose} autoFocus>
            Отмена
          </button>
          <button
            type="button"
            className="button danger"
            disabled={state.busy}
            onClick={() => void confirm()}
          >
            {state.busy ? "Удаление…" : "Удалить"}
          </button>
        </div>
      </section>
    </div>
  );
}
