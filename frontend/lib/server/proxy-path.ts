/**
 * Validates the catch-all path of the `/api/v1/*` proxy before it is forwarded.
 *
 * Next decodes each segment, so `auth%2Flogin` arrives as the single segment
 * "auth/login". Re-encoding it and comparing against a blocklist lets it through,
 * and the backend decodes it back to `/auth/login`. Every segment must therefore
 * be a plain id or slug; anything else is rejected rather than normalized.
 */
const SEGMENT = /^[A-Za-z0-9_~-][A-Za-z0-9._~-]*$/;

/** Returns the canonical backend path ("goals/8"), or null if any segment is unsafe. */
export function backendPath(segments: readonly string[]): string | null {
  if (segments.length === 0) return null;
  for (const segment of segments) {
    if (!SEGMENT.test(segment) || segment === "." || segment === "..") return null;
  }
  return segments.join("/");
}

/** Case-insensitive membership, so `AUTH/login` cannot dodge a block list either. */
export function matchesPath(path: string, set: ReadonlySet<string>): boolean {
  return set.has(path.toLowerCase());
}
