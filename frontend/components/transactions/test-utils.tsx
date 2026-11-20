/**
 * Test helpers for the transactions screens: a fresh SWR cache per render and a
 * URL-aware `next/navigation` mock whose `router.replace` really changes
 * `useSearchParams()` (so URL-synced filters and pagination can be exercised).
 */
import { render } from "@testing-library/react";
import { useSyncExternalStore } from "react";
import { SWRConfig } from "swr";
import { vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { Account, Bank, Category, Page, Transaction } from "@/lib/types";

export function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>,
  );
}

type Listener = () => void;
let params = new URLSearchParams();
const listeners = new Set<Listener>();

export const navigation = {
  setUrl(query: string) {
    params = new URLSearchParams(query);
    listeners.forEach((listener) => listener());
  },
  current: () => params,
  router: {
    push: vi.fn((url: string) => navigation.setUrl(url.split("?")[1] ?? "")),
    replace: vi.fn((url: string) => navigation.setUrl(url.split("?")[1] ?? "")),
    back: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  },
};

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Use as `vi.mock("next/navigation", () => navigationMock())`. */
export function navigationMock() {
  return {
    useRouter: () => navigation.router,
    usePathname: () => "/transactions",
    useSearchParams: () =>
      useSyncExternalStore(
        subscribe,
        () => params,
        () => params,
      ),
    useParams: () => ({}),
    redirect: vi.fn(),
    notFound: vi.fn(),
  };
}

export function apiError(status: number, code: string, fieldErrors: ApiError["fieldErrors"] = []) {
  return new ApiError({ status, code, fieldErrors });
}

export function page<T>(items: T[], total = items.length, limit = 20, offset = 0): Page<T> {
  return { items, total, limit, offset };
}

export const categories: Category[] = [
  {
    id: 1,
    name: "Продукты",
    color: "#22aa66",
    icon: "shopping-cart",
    kind: "expense",
    is_system: true,
  },
  { id: 2, name: "Зарплата", color: "#2266aa", icon: "briefcase", kind: "income", is_system: true },
  { id: 3, name: "Прочее", color: "#999999", icon: "dots", kind: "any", is_system: true },
];

export function account(overrides: Partial<Account> = {}): Account {
  return {
    id: 10,
    name: "Карта",
    account_type: "card",
    currency_code: "KZT",
    bank_id: 1,
    last4: null,
    is_archived: false,
    opening_balance: "0.00",
    opening_balance_at: "2026-01-01T00:00:00Z",
    balance: "1000.00",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export const banks: Bank[] = [{ id: 1, name: "Тестовый банк", logo: null }];

export function transaction(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 100,
    amount: "4500.00",
    currency_code: "KZT",
    description: "Покупка",
    transaction_type: "expense",
    transaction_date: "2026-11-10T09:30:00Z",
    category_id: 1,
    bank_id: null,
    account_id: 10,
    created_at: "2026-11-10T09:31:00Z",
    updated_at: "2026-11-10T09:31:00Z",
    ...overrides,
  };
}
