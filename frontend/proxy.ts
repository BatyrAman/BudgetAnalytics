/**
 * Route guard (Next.js 16 `proxy`, formerly middleware).
 * Pages of the application require a session cookie; without it the user is
 * sent to /login with a same-site `next` path. API routes are not matched here:
 * the API proxy answers 401 itself.
 */
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register", "/forgot-password", "/reset-password"];
const SESSION_COOKIE = "ba_rt";

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.some((path) => pathname === path)) return NextResponse.next();
  if (request.cookies.get(SESSION_COOKIE)?.value) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(url);
}

export const config = {
  // Everything except API routes, Next.js internals and static files.
  matcher: ["/((?!api/|_next/|favicon|icon|apple-icon|.*\\.(?:svg|png|jpg|ico|txt)$).*)"],
};
