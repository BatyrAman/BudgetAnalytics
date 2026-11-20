/**
 * Session endpoints: login, register, logout.
 * They call the backend, keep the token pair in httpOnly cookies and return
 * only `{ ok: true }` to the browser.
 */
import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import {
  REFRESH_COOKIE,
  backendBaseUrl,
  clearSessionCookies,
  forwardedHeaders,
  isTrustedMutation,
  jsonError,
  writeSessionCookies,
  type TokenPair,
} from "@/lib/server/session";

export const dynamic = "force-dynamic";

type Context = { params: Promise<{ action: string }> };

const UPSTREAM: Record<string, string> = {
  login: "/api/v1/auth/login",
  register: "/api/v1/auth/register",
};

export async function POST(request: NextRequest, context: Context): Promise<Response> {
  const { action } = await context.params;
  if (!isTrustedMutation(request)) {
    return jsonError(403, "csrf_rejected", "Cross-site request rejected");
  }
  const jar = await cookies();

  if (action === "logout") {
    const refreshToken = jar.get(REFRESH_COOKIE)?.value;
    if (refreshToken) {
      // Best effort: the session ends locally even if the backend is unreachable.
      await fetch(`${backendBaseUrl()}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...forwardedHeaders(request) },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      }).catch(() => undefined);
    }
    clearSessionCookies(jar);
    return new Response(null, { status: 204 });
  }

  const path = UPSTREAM[action];
  if (!path) return jsonError(404, "not_found", "Not Found");

  let payload: string;
  try {
    payload = JSON.stringify(await request.json());
  } catch {
    return jsonError(422, "validation_error", "Invalid JSON body");
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${backendBaseUrl()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...forwardedHeaders(request) },
      body: payload,
      cache: "no-store",
    });
  } catch {
    return jsonError(502, "backend_unavailable", "Backend unavailable");
  }

  if (!upstream.ok) {
    // Pass the backend error body (detail/code/request_id) through unchanged.
    const headers = new Headers({
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) headers.set("Retry-After", retryAfter);
    return new Response(await upstream.text(), { status: upstream.status, headers });
  }

  const tokens = (await upstream.json()) as TokenPair;
  writeSessionCookies(jar, tokens);
  return Response.json({ ok: true }, { status: 200, headers: { "Cache-Control": "no-store" } });
}
