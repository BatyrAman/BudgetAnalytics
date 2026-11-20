/**
 * Browser HTTP client. Talks only to the same-origin Next.js proxy (`/api/v1/*`),
 * which attaches the session from httpOnly cookies — tokens never reach JS.
 */
import { ApiError, errorFromResponse, networkError } from "./errors";

export type Query = Record<string, string | number | boolean | null | undefined>;

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  query?: Query;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
};

/** Event fired when the session cannot be restored; the app shell redirects to /login. */
export const SESSION_EXPIRED_EVENT = "ba:session-expired";

export function buildQuery(query: Query | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, json, form, signal } = options;
  const headers: Record<string, string> = {
    Accept: "application/json",
    // CSRF guard: the proxy rejects mutating requests without this header.
    "X-Requested-With": "fetch",
  };
  let body: BodyInit | undefined;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = form;
  }

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}${buildQuery(query)}`, {
      method,
      headers,
      body,
      signal,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw networkError();
  }

  if (!response.ok) {
    const apiError = await errorFromResponse(response);
    if (apiError.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
    }
    throw apiError;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Session endpoints handled by the Next.js server (they set/clear the cookies). */
export async function sessionRequest<T>(
  action: "login" | "register" | "logout",
  json?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/session/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "fetch" },
      body: json === undefined ? undefined : JSON.stringify(json),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw networkError();
  }
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export { ApiError };
