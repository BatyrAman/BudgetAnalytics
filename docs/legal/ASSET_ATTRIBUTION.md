# Asset Attribution

Inventory of fonts, icons, images and design assets used by BudgetAnalytics, as of 2026-11-20. The licenses were verified from the upstream sources or the installed packages, as noted.

## Fonts

| Asset | How it is used | License | Source | Attribution / conditions |
|---|---|---|---|---|
| **Inter** (Latin and Cyrillic subsets) | `next/font/google` in `frontend/app/layout.tsx`. The font files are downloaded **at build time** and served from the app's own origin; browsers do not contact Google at runtime. | SIL Open Font License 1.1, © 2016 The Inter Project Authors (verified from upstream `LICENSE.txt`) | <https://github.com/rsms/inter> | The font may be used, bundled and redistributed with software; it may not be sold on its own. Keep the copyright and OFL notice with redistributed font files. "Inter" is a Reserved Font Name only if the font is modified. |

The fallback fonts `Arial, sans-serif` come from the user's system and are not distributed.

## Icons

| Asset | How it is used | License | Source | Attribution / conditions |
|---|---|---|---|---|
| **Lucide** icons (`lucide-react` 1.75.0) | All UI icons, including the brand mark in the app header (the "Wallet" icon) | ISC, © Lucide Icons and Contributors. Icons derived from **Feather** are MIT, © 2013-present Cole Bemis (listed in the package's `LICENSE`). | <https://lucide.dev>, <https://github.com/lucide-icons/lucide> | Keep both notices; they ship with the package |

## Images in `frontend/public/`

| File | What it is | Referenced by the app | Ownership / license | Action |
|---|---|---|---|---|
| `icon.svg` | 180×180 rounded square drawing the characters "v0", the mark of Vercel's v0 templates | No: `frontend/app/layout.tsx` declares no icons. Files in `public/` are still served at `/icon.svg`. | **Third party (Vercel); not owned by this project.** Brand and trademark rights may apply. | **Replace with an original BudgetAnalytics icon, or remove** |
| `icon-light-32x32.png` | **Not a PNG.** The file contains base64 text of a PNG, so browsers cannot render it. | No | Unknown; most likely from the same v0 template | Confirm the origin; replace with real PNG files of an original icon |
| `icon-dark-32x32.png` | Same as above | No | Unknown | Same as above |
| `apple-icon.png` | Same as above (base64 text, 180×180) | No | Unknown | Same as above |

## Illustrations, photos and logos

None were found: no raster images, photos, illustrations, bank logos or external image URLs in the frontend source. Bank names are shown as text, and the bank "logo" in the UI is a monogram (for example "HB") generated from the name.

## External design sources

| Source | Status |
|---|---|
| **v0 (Vercel)** design prototype | The frontend was built from a v0-generated prototype (see `docs/design/v0/README.md`). Rights in v0 output are governed by Vercel's terms at the time of generation. **Not reviewed.** |
| **Figma** file referenced in `docs/design/` | Design specification only; no Figma-exported assets are in the repository |
| Design tokens (colours, spacing) in `frontend/app/globals.css` | Written for this project; no third-party design system copied, apart from base styles imported from `shadcn/tailwind.css` (MIT) |

## Owner actions

1. Replace `frontend/public/icon.svg` and the three `.png` files with original artwork, or with assets whose license allows the use, and record the source here.
2. If a logo is commissioned, keep the designer's assignment or license in the project records.
3. Confirm the review of the v0 terms for the generated prototype ([LICENSING_DECISION.md](LICENSING_DECISION.md) §2).
