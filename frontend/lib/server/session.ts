import "server-only";

/**
 * Server-side session handling for the Next.js backend-for-frontend.
 *
 * The FastAPI backend issues Bearer access tokens and single-use (rotating)
 * refresh tokens. Both are kept in httpOnly cookies so that browser JavaScript
 * never sees them. This module contains no business logic.
 */

export const ACCESS_COOKIE = "ba_at";
export const REFRESH_COOKIE = "ba_rt";

/** Fallback lifetimes when the token carries no readable `exp` (backend defaults). */
const ACCESS_FALLBACK_SECONDS = 30 * 60;
const REFRESH_FALLBACK_SECONDS = 7 * 24 * 60 * 60;

export function backendBaseUrl(): string {
  const url = process.env.BACKEND_URL;
  if (!url) throw new Error("BACKEND_URL is not configured");
  return url.replace(/\/+$/, "");
}

export type TokenPair = { access_token: string; refresh_token: string };

/** Seconds until the JWT `exp` claim (not verified — used only for cookie lifetime). */
export function secondsUntilExpiry(token: string, fallback: number): number {
  try {
    const payload = token.split(".")[1];
    if (!payload) return fallback;
    const json = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      exp?: number;
    };
    if (typeof json.exp !== "number") return fallback;
    return Math.max(0, Math.floor(json.exp - Date.now() / 1000));
  } catch {
    return fallback;
  }
}

type CookieOptions = {
  httpOnly: true;
  secure: boolean;
  sameSite: "strict";
  path: string;
  maxAge: number;
};

function cookieOptions(maxAge: number): CookieOptions {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge,
  };
}

type CookieWriter = {
  set: (name: string, value: string, options: CookieOptions) => unknown;
};

export function writeSessionCookies(cookies: CookieWriter, tokens: TokenPair): void {
  cookies.set(
    ACCESS_COOKIE,
    tokens.access_token,
    cookieOptions(secondsUntilExpiry(tokens.access_token, ACCESS_FALLBACK_SECONDS)),
  );
  cookies.set(
    REFRESH_COOKIE,
    tokens.refresh_token,
    cookieOptions(secondsUntilExpiry(tokens.refresh_token, REFRESH_FALLBACK_SECONDS)),
  );
}

export function clearSessionCookies(cookies: CookieWriter): void {
  cookies.set(ACCESS_COOKIE, "", cookieOptions(0));
  cookies.set(REFRESH_COOKIE, "", cookieOptions(0));
}

/**
 * CSRF guard for mutating requests: the session cookies are SameSite=Strict,
 * and in addition the request must be same-origin and carry the custom header
 * that cross-site forms cannot set.
 */
export function isTrustedMutation(request: Request): boolean {
  if (request.headers.get("x-requested-with") !== "fetch") return false;
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") return false;
  const origin = request.headers.get("origin");
  if (origin) {
    const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
    try {
      if (new URL(origin).host !== host) return false;
    } catch {
      return false;
    }
  }
  return true;
}

/** Headers forwarded to the backend so its per-IP rate limits see the real client. */
export function forwardedHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers["X-Request-ID"] = requestId;
  const forwardedFor = request.headers.get("x-forwarded-for");
  const realIp = request.headers.get("x-real-ip");
  const client = forwardedFor ?? realIp;
  if (client) headers["X-Forwarded-For"] = client;
  return headers;
}

// Refresh tokens are single-use: concurrent refreshes with the same token would
// trigger the backend's reuse detection and revoke the session. Deduplicate
// in-flight refreshes per token and remember the result briefly.
type RefreshResult = { ok: true; tokens: TokenPair } | { ok: false; status: number };
const inflight = new Map<string, { promise: Promise<RefreshResult>; expires: number }>();
const REFRESH_REUSE_WINDOW_MS = 10_000;

export function refreshTokens(refreshToken: string, request: Request): Promise<RefreshResult> {
  const now = Date.now();
  for (const [key, entry] of inflight) if (entry.expires < now) inflight.delete(key);
  const cached = inflight.get(refreshToken);
  if (cached) return cached.promise;

  const promise = (async (): Promise<RefreshResult> => {
    try {
      const response = await fetch(`${backendBaseUrl()}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...forwardedHeaders(request) },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
      if (!response.ok) return { ok: false, status: response.status };
      return { ok: true, tokens: (await response.json()) as TokenPair };
    } catch {
      return { ok: false, status: 502 };
    }
  })();
  inflight.set(refreshToken, { promise, expires: now + REFRESH_REUSE_WINDOW_MS });
  return promise;
}

export function jsonError(status: number, code: string, detail: string): Response {
  return Response.json({ detail, code, request_id: null }, { status });
}
