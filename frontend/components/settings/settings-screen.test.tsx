import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getMe } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { SettingsScreen } from "./settings-screen";

const nav = vi.hoisted(() => ({
  params: new URLSearchParams(),
  router: { push: vi.fn(), replace: vi.fn() },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => nav.router,
  useSearchParams: () => nav.params,
  usePathname: () => "/settings",
}));

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
}));

function renderScreen() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <SettingsScreen />
    </SWRConfig>,
  );
}

// Generous timeout: jsdom renders are slow on a loaded CI/dev machine.
describe("SettingsScreen routing", () => {
  beforeEach(() => {
    nav.params = new URLSearchParams();
    nav.router.push.mockClear();
    vi.mocked(getMe).mockRejectedValue(new ApiError({ status: 500, code: "http_500" }));
  });

  it("opens «Общие» when no section is given", () => {
    renderScreen();
    expect(screen.getByRole("heading", { name: "Общие" })).toBeInTheDocument();
  });

  it("opens the section from the URL (direct link / refresh)", () => {
    nav.params = new URLSearchParams("section=security");
    renderScreen();
    expect(screen.getByRole("heading", { name: "Безопасность" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Все разделы/ })).toBeInTheDocument();
  });

  it("ignores unknown sections", () => {
    nav.params = new URLSearchParams("section=toString");
    renderScreen();
    expect(screen.getByRole("heading", { name: "Общие" })).toBeInTheDocument();
  });

  it("navigates to a section via the URL", async () => {
    renderScreen();
    const [desktopTab] = screen.getAllByRole("button", { name: /Оформление/ });
    await userEvent.click(desktopTab);
    expect(nav.router.push).toHaveBeenCalledWith("/settings?section=appearance", { scroll: false });
  });
});
