"use client";

import { useState } from "react";

import { createCategory, updateCategory, type CategoryInput } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import type { Category, CategoryKind } from "@/lib/types";

import {
  CATEGORY_ICONS,
  CATEGORY_KIND_LABEL,
  CATEGORY_PALETTE,
  CategoryIcon,
} from "./category-icons";
import "./categories.css";

type FieldName = "name" | "kind" | "color" | "icon";
type Errors = Partial<Record<FieldName | "form", string>>;

const FIELD_NAMES: FieldName[] = ["name", "kind", "color", "icon"];

/** Map an API failure to field / form messages (C-2). */
export function categoryErrors(error: unknown): Errors {
  if (!(error instanceof ApiError)) return { form: toUserMessage(error) };
  if (error.code === "category_exists") return { name: toUserMessage(error) };
  if (error.code === "category_kind_conflict") return { kind: toUserMessage(error) };
  const errors: Errors = {};
  for (const item of error.fieldErrors) {
    const field = FIELD_NAMES.find((name) => name === item.field);
    if (field) errors[field] = item.message;
  }
  if (Object.keys(errors).length === 0) errors.form = toUserMessage(error);
  return errors;
}

export function CategoryForm({
  category,
  onClose,
  onSaved,
}: {
  category?: Category;
  onClose: () => void;
  onSaved: () => Promise<unknown> | void;
}) {
  const [name, setName] = useState(category?.name ?? "");
  const [kind, setKind] = useState<CategoryKind>(category?.kind ?? "expense");
  const [color, setColor] = useState(category?.color ?? CATEGORY_PALETTE[0]);
  const [icon, setIcon] = useState(category?.icon ?? "shopping-cart");
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const knownColor = CATEGORY_PALETTE.some((value) => value === color);
  const knownIcon = CATEGORY_ICONS.some((item) => item.slug === icon);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 2 || trimmed.length > 100) {
      setErrors({ name: "Название должно содержать от 2 до 100 символов." });
      return;
    }
    const input: CategoryInput = { name: trimmed, kind, color, icon };
    setBusy(true);
    setErrors({});
    try {
      if (category) await updateCategory(category.id, input);
      else await createCategory(input);
      await onSaved();
      onClose();
    } catch (error) {
      setErrors(categoryErrors(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="overlay-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className="demo-dialog category-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="category-form-title"
      >
        <button type="button" className="dialog-close" onClick={onClose} aria-label="Закрыть">
          ×
        </button>
        <h2 id="category-form-title">{category ? "Изменить категорию" : "Новая категория"}</h2>
        <form className="entity-form" onSubmit={submit} noValidate>
          <label className="field-label">
            Название *
            <input
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "category-name-error" : undefined}
              autoFocus
            />
            {errors.name && (
              <small id="category-name-error" className="field-error" role="alert">
                {errors.name}
              </small>
            )}
          </label>
          <label className="field-label">
            Тип
            <select
              value={kind}
              onChange={(event) => {
                const value = event.target.value;
                if (value === "expense" || value === "income" || value === "any") setKind(value);
              }}
              aria-invalid={Boolean(errors.kind)}
            >
              <option value="expense">Расход</option>
              <option value="income">Доход</option>
              <option value="any">Любой тип</option>
            </select>
            {errors.kind && (
              <small className="field-error" role="alert">
                {errors.kind}
              </small>
            )}
          </label>
          <div className="field-label">
            <span id="category-color-label">Цвет</span>
            <div className="color-palette" role="radiogroup" aria-labelledby="category-color-label">
              {!knownColor && (
                <button
                  type="button"
                  role="radio"
                  aria-checked
                  aria-label={`Текущий цвет ${color}`}
                  className="selected"
                  style={{ backgroundColor: color }}
                />
              )}
              {CATEGORY_PALETTE.map((value) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-label={`Цвет ${value}`}
                  aria-checked={color === value}
                  className={color === value ? "selected" : ""}
                  style={{ backgroundColor: value }}
                  onClick={() => setColor(value)}
                />
              ))}
            </div>
            {errors.color && <small className="field-error">{errors.color}</small>}
          </div>
          <div className="field-label">
            <span id="category-icon-label">Иконка</span>
            <div className="icon-picker" role="radiogroup" aria-labelledby="category-icon-label">
              {!knownIcon && (
                <button
                  type="button"
                  role="radio"
                  aria-checked
                  aria-label="Текущая иконка"
                  className="selected"
                >
                  <CategoryIcon icon={icon} color={undefined} className="" />
                </button>
              )}
              {CATEGORY_ICONS.map(({ slug, label, Icon }) => (
                <button
                  key={slug}
                  type="button"
                  role="radio"
                  aria-label={label}
                  aria-checked={icon === slug}
                  className={icon === slug ? "selected" : ""}
                  onClick={() => setIcon(slug)}
                >
                  <Icon aria-hidden="true" />
                </button>
              ))}
            </div>
            {errors.icon && <small className="field-error">{errors.icon}</small>}
          </div>
          <div className="category-preview">
            <CategoryIcon icon={icon} color={color} />
            <span>{name.trim() || "Название категории"}</span>
            <small>{CATEGORY_KIND_LABEL[kind]}</small>
          </div>
          {errors.form && (
            <p className="form-error" role="alert">
              {errors.form}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="button secondary" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="button primary" disabled={busy}>
              {busy ? "Сохранение…" : "Сохранить"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
