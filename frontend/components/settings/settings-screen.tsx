"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { AppearanceSection } from "./appearance-section";
import { GeneralSection } from "./general-section";
import { SecuritySection } from "./security-section";

export type SettingsSection = "general" | "appearance" | "security";

const SECTION_LABELS: Record<SettingsSection, string> = {
  general: "Общие",
  appearance: "Оформление",
  security: "Безопасность",
};
const SECTIONS = Object.keys(SECTION_LABELS) as SettingsSection[];

function parseSection(value: string | null): SettingsSection | null {
  return SECTIONS.find((section) => section === value) ?? null;
}

/**
 * Sections are addressed by `?section=` so a direct URL and a refresh open the same
 * section. On mobile, no section → list of sections; a section → its own screen.
 */
export function SettingsScreen() {
  const router = useRouter();
  const requested = parseSection(useSearchParams().get("section"));
  const active = requested ?? "general";

  const open = (section: SettingsSection) =>
    router.push(`/settings?section=${section}`, { scroll: false });

  const sectionButtons = (isMobile: boolean) =>
    SECTIONS.map((section) => (
      <button
        type="button"
        key={section}
        className={active === section && !isMobile ? "selected" : ""}
        aria-current={active === section && !isMobile ? "page" : undefined}
        onClick={() => open(section)}
      >
        {SECTION_LABELS[section]} {isMobile && <span aria-hidden="true">›</span>}
      </button>
    ));

  return (
    <div className="settings-page">
      <nav className="settings-tabs" aria-label="Разделы настроек">
        {sectionButtons(false)}
      </nav>
      <nav
        className={`settings-mobile-index ${requested ? "hidden" : ""}`}
        aria-label="Разделы настроек"
      >
        <h2>Настройки</h2>
        <p>Выберите раздел</p>
        <div>{sectionButtons(true)}</div>
      </nav>
      {requested && (
        <button
          type="button"
          className="settings-mobile-back"
          onClick={() => router.push("/settings")}
        >
          <ChevronLeft aria-hidden="true" /> Все разделы
        </button>
      )}
      <div className={`settings-content ${requested ? "mobile-active" : ""}`}>
        {active === "general" && <GeneralSection />}
        {active === "appearance" && <AppearanceSection />}
        {active === "security" && <SecuritySection />}
      </div>
    </div>
  );
}
