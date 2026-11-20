import { createElement } from "react";
import { CircleHelp } from "lucide-react";

import { categoryIcon } from "@/components/category-glyph";
import type { Category } from "@/lib/types";

/** Category name with its colour dot and icon; "—" when the category is unknown. */
export function CategoryCell({ category }: { category: Category | undefined }) {
  // Unknown category (deleted or not loaded) → question mark; unknown icon slug → wallet.
  const icon = category ? categoryIcon(category.icon) : CircleHelp;
  return (
    <span className="category-cell">
      <i style={{ background: category?.color ?? "var(--border-strong)" }}>
        {createElement(icon, { size: 14, "aria-hidden": true })}
      </i>
      {category?.name ?? "—"}
    </span>
  );
}
