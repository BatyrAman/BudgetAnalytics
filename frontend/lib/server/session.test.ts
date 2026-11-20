import { afterEach, describe, expect, it, vi } from "vitest";

import { isTrustedMutation, refreshTokens, secondsUntilExpiry } from "./session";
import { safeNextPath } from "@/components/auth-screen";

function jwtWithExp(exp: number): string {
  const payload = Buffer.from(JSON.stringify({ sub: "1", exp })).toString("base64url");
  return `header.${payload}.signature`;
}

function request(headers: Record<string, string>) {
  return new Request("https://app.example.kz/api/v1/transactions", { method: "POST", headers });
}

describe("isTrustedMutation (CSRF guard)", () => {
  it("accepts same-origin fetches with the custom header", () => {
    expect(
      isTrustedMutation(
        request({
          "x-requested-with": "fetch",
          "sec-fetch-site": "same-origin",
          origin: "https://app.example.kz",
          host: "app.example.kz",
        }),
      ),
    ).toBe(true);
  });

  it("rejects cross-site requests and requests without the header", () => {
    expect(
      isTrustedMutation(request({ origin: "https://app.example.kz", host: "app.example.kz" })),
    ).toBe(false);
    expect(
      isTrustedMutation(request({ "x-requested-with": "fetch", "sec-fetch-site": "cross-site" })),
    ).toBe(false);
    expect(
      isTrustedMutation(
        request({
          "x-requested-with": "fetch",
          origin: "https://evil.example",
          host: "app.example.kz",
        }),
      ),
    ).toBe(false);
  });
});

describe("secondsUntilExpiry", () => {
  it("reads exp for cookie lifetime and falls back for unreadable tokens", () => {
    const now = Math.floor(Date.now() / 1000);
    expect(secondsUntilExpiry(jwtWithExp(now + 1800), 60)).toBeGreaterThan(1790);
    expect(secondsUntilExpiry(jwtWithExp(now - 10), 60)).toBe(0);
    expect(secondsUntilExpiry("not-a-jwt", 60)).toBe(60);
  });
});

describe("refreshTokens", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("sends one backend refresh for concurrent callers with the same single-use token", async () => {
    vi.stubEnv("BACKEND_URL", "http://backend.test");
    const fetchMock = vi.fn(async () =>
      Response.json({ access_token: "new-access", refresh_token: "new-refresh" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const incoming = new Request("http://app.test/api/v1/goals");
    const token = `refresh-${Math.random()}`;

    const [first, second] = await Promise.all([
      refreshTokens(token, incoming),
      refreshTokens(token, incoming),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first).toEqual(second);
    expect(first).toMatchObject({ ok: true, tokens: { access_token: "new-access" } });
  });

  it("reports a failed refresh without throwing", async () => {
    vi.stubEnv("BACKEND_URL", "http://backend.test");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 401 })),
    );
    const result = await refreshTokens(`expired-${Math.random()}`, new Request("http://app.test/"));
    expect(result).toEqual({ ok: false, status: 401 });
  });
});

describe("safeNextPath (open redirect protection)", () => {
  it.each([
    ["/transactions?category_id=3", "/transactions?category_id=3"],
    [null, "/dashboard"],
    ["https://evil.example", "/dashboard"],
    ["//evil.example", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
  ])("%s → %s", (next, expected) => {
    expect(safeNextPath(next)).toBe(expected);
  });
});
