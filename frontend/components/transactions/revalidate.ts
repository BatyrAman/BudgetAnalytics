import type { ScopedMutator } from "swr";

/**
 * SWR cache keys whose data depends on transactions. After a create/edit/delete
 * (or a committed import) they are revalidated: account balances, budgets usage,
 * dashboard and analytics are all computed by the backend from transactions.
 */
const DEPENDENT_KEYS = new Set([
  "transactions",
  "transaction",
  "accounts",
  "account",
  "overview",
  "summary",
  "savings-rate",
  "category-breakdown",
  "monthly",
  "comparison",
  "budget-utilization",
]);

export function isTransactionDependentKey(key: unknown): boolean {
  return Array.isArray(key) && typeof key[0] === "string" && DEPENDENT_KEYS.has(key[0]);
}

/** Revalidate everything derived from transactions; `deletedId` is dropped instead. */
export function revalidateTransactionData(mutate: ScopedMutator, deletedId?: number) {
  return mutate((key: unknown) => {
    if (
      deletedId !== undefined &&
      Array.isArray(key) &&
      key[0] === "transaction" &&
      key[1] === deletedId
    )
      return false;
    return isTransactionDependentKey(key);
  });
}
