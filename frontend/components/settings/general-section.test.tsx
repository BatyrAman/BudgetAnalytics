import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import useSWR, { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getMe } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { User } from "@/lib/types";
import { GeneralSection } from "./general-section";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
}));

const user: User = {
  id: 7,
  full_name: "Тестовый Пользователь",
  email: "user@example.com",
  is_active: true,
  default_currency_code: "KZT",
  created_at: "2025-03-04T10:00:00Z",
  updated_at: "2025-03-04T10:00:00Z",
};

/** Another cached request elsewhere in the app; must be refetched after a time-zone change. */
const otherFetcher = vi.fn(async () => "ok");
function OtherData() {
  useSWR(["dashboard", "summary"], otherFetcher);
  return null;
}

function renderSection() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <GeneralSection />
      <OtherData />
    </SWRConfig>,
  );
}

// Generous timeout: jsdom renders are slow on a loaded CI/dev machine.
describe("GeneralSection", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(getMe).mockResolvedValue(user);
  });

  it("shows the read-only profile and default currency", async () => {
    renderSection();
    expect(await screen.findByText("Тестовый Пользователь")).toBeInTheDocument();
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("04.03.2025")).toBeInTheDocument();
    expect(screen.getByText("KZT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Изменить профиль" })).toBeDisabled();
  });

  it("shows a Russian error with retry when the profile fails", async () => {
    vi.mocked(getMe).mockRejectedValue(new ApiError({ status: 503, code: "backend_unavailable" }));
    renderSection();
    expect(await screen.findByText("Сервер недоступен. Попробуйте позже.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Повторить/ })).toBeInTheDocument();
  });

  it("reads the stored time zone", async () => {
    window.localStorage.setItem("ba:timezone", "Asia/Oral");
    renderSection();
    await waitFor(() => expect(screen.getByLabelText("Часовой пояс")).toHaveValue("Asia/Oral"));
  });

  it("persists the time zone to ba:timezone and revalidates all SWR data", async () => {
    renderSection();
    await screen.findByText("Тестовый Пользователь");
    await waitFor(() => expect(otherFetcher).toHaveBeenCalledTimes(1));
    const meCalls = vi.mocked(getMe).mock.calls.length;

    await userEvent.selectOptions(screen.getByLabelText("Часовой пояс"), "Asia/Aqtobe");

    expect(window.localStorage.getItem("ba:timezone")).toBe("Asia/Aqtobe");
    expect(screen.getByText("Сохраняется в этом браузере")).toBeInTheDocument();
    await waitFor(() => expect(otherFetcher).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(vi.mocked(getMe).mock.calls.length).toBeGreaterThan(meCalls));
  });
});
