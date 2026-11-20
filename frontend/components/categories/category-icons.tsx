import { createElement } from "react";

import { CATEGORY_ICONS, categoryIcon } from "@/components/category-glyph";

import type { CategoryKind } from "@/lib/types";

/** 12-colour palette for user categories (C-2). */
export const CATEGORY_PALETTE = [
  "#176B55",
  "#4776C7",
  "#D69A35",
  "#7A6BD1",
  "#C65353",
  "#1686A0",
  "#8A5AB5",
  "#B66A32",
  "#467C45",
  "#A34478",
  "#607D8B",
  "#526070",
] as const;

export { CATEGORY_ICONS, categoryIcon };

export const CATEGORY_KIND_LABEL: Record<CategoryKind, string> = {
  expense: "Расход",
  income: "Доход",
  any: "Любой тип",
};

/** Lowest WCAG contrast of the swatch against white or dark text (visual only). */
export function swatchContrast(hex: string): number {
  const channels = (hex.match(/[A-Fa-f0-9]{2}/g) ?? ["00", "00", "00"])
    .map((part) => parseInt(part, 16) / 255)
    .map((n) => (n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4));
  const luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  return Math.min(1.05 / (luminance + 0.05), (luminance + 0.05) / 0.05);
}

export function CategoryIcon({
  icon,
  color,
  className = "category-icon",
}: {
  icon: string | undefined;
  color: string | undefined;
  className?: string;
}) {
  const lowContrast = color ? swatchContrast(color) < 3 : false;
  return (
    <span
      className={`${className}${lowContrast ? " border-strong" : ""}`}
      style={color ? { backgroundColor: color } : undefined}
      aria-hidden="true"
    >
      {createElement(categoryIcon(icon))}
    </span>
  );
}
