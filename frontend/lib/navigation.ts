/**
 * Full-page navigation for session boundaries (login, logout, expired session,
 * password change). A hard load guarantees that:
 *  - the route guard sees the new session cookies (a client-side transition may
 *    reuse a redirect prefetched before the user signed in);
 *  - no data of the previous user survives in the in-memory SWR cache.
 */
export function navigateWithFullReload(path: string): void {
  window.location.assign(path);
}
