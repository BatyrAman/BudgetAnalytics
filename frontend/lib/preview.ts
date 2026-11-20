"use client";

import { useSearchParams } from "next/navigation";

/**
 * Design-review helpers. The «Демо: состояние» switcher and demo toggles exist
 * only in development builds; production always renders real data states.
 */
export const PREVIEW_ENABLED = process.env.NODE_ENV !== "production";

export type PreviewState = "default" | "loading" | "empty" | "error";

export function usePreviewState(): PreviewState {
  const params = useSearchParams();
  if (!PREVIEW_ENABLED) return "default";
  const value = params.get("state");
  return value === "loading" || value === "empty" || value === "error" ? value : "default";
}
