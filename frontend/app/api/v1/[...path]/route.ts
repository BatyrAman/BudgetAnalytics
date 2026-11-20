/**
 * Same-origin proxy to the FastAPI backend (`BACKEND_URL/api/v1/*`).
 * Attaches the access token from the httpOnly cookie, refreshes it once on 401,
 * and never exposes tokens to the browser. No business logic lives here.
 */
import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  backendBaseUrl,
  clearSessionCookies,
  forwardedHeaders,
  isTrustedMutation,
  jsonError,
  refreshTokens,
  writeSessionCookies,
} from "@/lib/server/session";
import { backendPath, matchesPath } from "@/lib/server/proxy-path";

export const dynamic = "force-dynamic";

/** Token-issuing endpoints are served by /api/session/* so tokens never reach JS. */
const BLOCKED = new Set([
  "auth/login",
  "auth/register",
  "auth/refresh",
  "auth/token",
  "auth/logout",
]);
/** Successful calls to these end every session; drop the cookies too. */
const ENDS_SESSION = new Set(["auth/change-password", "auth/logout-all"]);
/** Statement uploads (5 MB backend limit) plus multipart overhead. */
const MAX_BODY_BYTES = 6 * 1024 * 1024;
const PASS_THROUGH_RESPONSE_HEADERS = ["content-type", "x-request-id", "retry-after"];

type Context = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  const joined = backendPath(path);
  if (joined === null || matchesPath(joined, BLOCKED)) {
    return jsonError(404, "not_found", "Not Found");
  }

  const method = request.method.toUpperCase();
  if (method !== "GET" && method !== "HEAD" && !isTrustedMutation(request)) {
    return jsonError(403, "csrf_rejected", "Cross-site request rejected");
  }

  let body: ArrayBuffer | undefined;
  if (method !== "GET" && method !== "HEAD") {
    const declared = Number(request.headers.get("content-length") ?? "0");
    if (declared > MAX_BODY_BYTES) {
      return jsonError(413, "payload_too_large", "Request body too large");
    }
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return jsonError(413, "payload_too_large", "Request body too large");
    }
  }

  const jar = await cookies();
  const target = `${backendBaseUrl()}/api/v1/${joined}${request.nextUrl.search}`;
  const send = (accessToken: string | undefined) => {
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...forwardedHeaders(request),
    };
    const contentType = request.headers.get("content-type");
    if (contentType) headers["Content-Type"] = contentType;
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return fetch(target, { method, headers, body, cache: "no-store", redirect: "manual" });
  };

  let upstream: Response;
  try {
    upstream = await send(jar.get(ACCESS_COOKIE)?.value);
    const refreshToken = jar.get(REFRESH_COOKIE)?.value;
    if (upstream.status === 401 && refreshToken) {
      const refreshed = await refreshTokens(refreshToken, request);
      if (refreshed.ok) {
        writeSessionCookies(jar, refreshed.tokens);
        upstream = await send(refreshed.tokens.access_token);
      } else {
        clearSessionCookies(jar);
      }
    }
  } catch {
    return jsonError(502, "backend_unavailable", "Backend unavailable");
  }

  if (upstream.ok && matchesPath(joined, ENDS_SESSION)) clearSessionCookies(jar);

  const headers = new Headers();
  for (const name of PASS_THROUGH_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("Cache-Control", "no-store");
  return new Response(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    headers,
  });
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
