import { render } from "@testing-library/react";
import { Ellipsis, ShoppingCart, Wallet } from "lucide-react";
import { describe, expect, it } from "vitest";

import { CategoryIcon as AnalyticsIcon } from "@/components/analytics/category-icon";
import { CATEGORY_ICONS, categoryIcon } from "@/components/category-glyph";
import { CategoryIcon as SwatchIcon } from "@/components/categories/category-icons";

describe("categoryIcon (single slug → icon map)", () => {
  it("resolves backend slugs, aliases and unknown slugs per DESIGN_SYSTEM_SPEC §5", () => {
    expect(categoryIcon("shopping-cart")).toBe(ShoppingCart);
    // «Прочие расходы» is seeded with `dots`; Analytics used to show a wallet for it.
    expect(categoryIcon("dots")).toBe(Ellipsis);
    expect(categoryIcon("ellipsis")).toBe(Ellipsis);
    expect(categoryIcon("unknown-slug")).toBe(Wallet);
    expect(categoryIcon(undefined)).toBe(Wallet);
  });

  it("covers all 16 icon slugs of the seeded system categories", () => {
    const seeded = [
      "shopping-cart",
      "utensils",
      "car",
      "home",
      "wifi",
      "heart",
      "shirt",
      "book",
      "film",
      "gift",
      "credit-card",
      "dots",
      "briefcase",
      "plus",
      "repeat",
      "wallet",
    ];
    const known = new Set(CATEGORY_ICONS.map((item) => item.slug));
    expect(seeded.filter((slug) => !known.has(slug))).toEqual([]);
  });

  it("renders the same glyph for a category on every screen", () => {
    const analytics = render(<AnalyticsIcon name="dots" />).container.innerHTML;
    const swatch = render(<SwatchIcon icon="dots" color="#176B55" />).container.querySelector(
      "svg",
    );
    expect(swatch?.getAttribute("class")).toBe(
      new DOMParser()
        .parseFromString(analytics, "text/html")
        .querySelector("svg")
        ?.getAttribute("class"),
    );
  });
});
