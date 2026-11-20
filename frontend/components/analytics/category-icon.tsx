import { createElement } from "react";

import { categoryIcon } from "@/components/category-glyph";

/** Category icon by the backend icon name; a wallet for unknown names. */
export function CategoryIcon({ name }: { name?: string }) {
  return createElement(categoryIcon(name), { size: 15, "aria-hidden": true });
}
