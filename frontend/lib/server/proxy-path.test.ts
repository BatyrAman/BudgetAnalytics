import { describe, expect, it } from "vitest";

import { backendPath, matchesPath } from "./proxy-path";

const BLOCKED = new Set(["auth/login", "auth/refresh"]);

describe("backendPath", () => {
  it.each([
    [["goals", "8"], "goals/8"],
    [["budgets", "utilization"], "budgets/utilization"],
    [["imports", "kaspi_gold", "preview"], "imports/kaspi_gold/preview"],
    [["auth", "me"], "auth/me"],
  ])("accepts %j", (segments, expected) => {
    expect(backendPath(segments)).toBe(expected);
  });

  it.each([
    // Regression: Next decodes `auth%2Flogin` into ONE segment that the backend
    // would decode back into /auth/login, bypassing the token-endpoint block.
    [["auth/login"]],
    [["auth%2Flogin"]],
    [["auth\\login"]],
    [["x", ".."]],
    [["."]],
    [["goals", ""]],
    [["goals", ".hidden"]],
    [["goals", "8?x=1"]],
    [["goals", "8#x"]],
    [[]],
  ])("rejects %j", (segments) => {
    expect(backendPath(segments)).toBeNull();
  });
});

describe("matchesPath", () => {
  it("matches regardless of case", () => {
    expect(matchesPath("AUTH/Login", BLOCKED)).toBe(true);
    expect(matchesPath("auth/me", BLOCKED)).toBe(false);
  });
});
