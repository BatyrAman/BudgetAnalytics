"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { LockKeyhole } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { useCategories } from "@/lib/api/hooks";
import { usePreviewState } from "@/lib/preview";
import type { Category } from "@/lib/types";

import { CATEGORY_KIND_LABEL, CategoryIcon } from "./category-icons";
import { CategoryForm } from "./category-form";
import { DeleteCategoryDialog } from "./delete-category-dialog";
import "./categories.css";

type Tab = "expense" | "income";

/** Revalidate every categories list (all kinds) after a mutation. */
export function useRevalidateCategories() {
  const { mutate } = useSWRConfig();
  return () => mutate((key) => Array.isArray(key) && key[0] === "categories");
}

function CategoryActions({
  category,
  onEdit,
  onDelete,
}: {
  category: Category;
  onEdit: () => void;
  onDelete: () => void;
}) {
  if (category.is_system) {
    return (
      <span className="system-hint" title="Системные категории нельзя изменить">
        Только чтение
      </span>
    );
  }
  return (
    <span className="row-actions">
      <button type="button" onClick={onEdit} aria-label={`Изменить «${category.name}»`}>
        Изменить
      </button>
      <button
        type="button"
        className="text-negative"
        onClick={onDelete}
        aria-label={`Удалить «${category.name}»`}
      >
        Удалить
      </button>
    </span>
  );
}

function CategoryTable({
  categories,
  onEdit,
  onDelete,
}: {
  categories: Category[];
  onEdit: (category: Category) => void;
  onDelete: (category: Category) => void;
}) {
  return (
    <div className="category-table card-surface">
      <table>
        <thead>
          <tr>
            <th scope="col">Категория</th>
            <th scope="col">Тип</th>
            <th scope="col">Владелец</th>
            <th scope="col" className="align-right">
              Действия
            </th>
          </tr>
        </thead>
        <tbody>
          {categories.map((category) => (
            <tr key={category.id}>
              <td>
                <span className="category-name">
                  <CategoryIcon icon={category.icon} color={category.color} />
                  <b>{category.name}</b>
                </span>
              </td>
              <td>{CATEGORY_KIND_LABEL[category.kind]}</td>
              <td>
                {category.is_system ? (
                  <span className="category-owner">
                    <LockKeyhole aria-hidden="true" />
                    Системная
                  </span>
                ) : (
                  "Своя"
                )}
              </td>
              <td className="align-right">
                <CategoryActions
                  category={category}
                  onEdit={() => onEdit(category)}
                  onDelete={() => onDelete(category)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="category-mobile-list">
        {categories.map((category) => (
          <article key={category.id} className="category-mobile-item">
            <div className="category-mobile-top">
              <CategoryIcon icon={category.icon} color={category.color} />
              <div>
                <b>{category.name}</b>
                <small>
                  {CATEGORY_KIND_LABEL[category.kind]} ·{" "}
                  {category.is_system ? (
                    <>
                      <LockKeyhole aria-hidden="true" size={12} /> Системная
                    </>
                  ) : (
                    "Своя"
                  )}
                </small>
              </div>
            </div>
            {!category.is_system && (
              <CategoryActions
                category={category}
                onEdit={() => onEdit(category)}
                onDelete={() => onDelete(category)}
              />
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

export function CategoriesScreen() {
  const [tab, setTab] = useState<Tab>("expense");
  const [form, setForm] = useState<{ category?: Category } | null>(null);
  const [removing, setRemoving] = useState<Category | null>(null);
  const preview = usePreviewState();
  const { data, error, isLoading, mutate } = useCategories(tab);
  const revalidate = useRevalidateCategories();

  const categories = preview === "empty" ? [] : (data ?? []);
  const showError = preview === "error" || Boolean(error);
  const showLoading = preview === "loading" || (isLoading && !data);
  const openCreate = () => setForm({});

  return (
    <AppShell>
      <div className="entity-page category-page">
        <PageHeader
          title="Категории"
          description="Системные категории и ваши собственные"
          actions={
            <button type="button" className="button primary" onClick={openCreate}>
              + Создать категорию
            </button>
          }
        />
        <div className="category-tabs" role="tablist" aria-label="Тип категорий">
          {(["expense", "income"] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              className={tab === value ? "active" : ""}
              onClick={() => setTab(value)}
            >
              {value === "expense" ? "Расходы" : "Доходы"}
            </button>
          ))}
        </div>
        {showError ? (
          <ErrorState error={error} retry={() => void mutate()} />
        ) : showLoading ? (
          <div className="account-grid" aria-busy="true">
            {[1, 2, 3].map((item) => (
              <SkeletonCard key={item} />
            ))}
          </div>
        ) : categories.length === 0 ? (
          <EmptyState
            description="Создайте свою категорию, если системных не хватает"
            action={
              <button type="button" className="button primary" onClick={openCreate}>
                Создать категорию
              </button>
            }
          />
        ) : (
          <CategoryTable
            categories={categories}
            onEdit={(category) => setForm({ category })}
            onDelete={setRemoving}
          />
        )}
        {form && (
          <CategoryForm
            category={form.category}
            onClose={() => setForm(null)}
            onSaved={revalidate}
          />
        )}
        {removing && (
          <DeleteCategoryDialog
            category={removing}
            onClose={() => setRemoving(null)}
            onDeleted={revalidate}
          />
        )}
      </div>
    </AppShell>
  );
}
