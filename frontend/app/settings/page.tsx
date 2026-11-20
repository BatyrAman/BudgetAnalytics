import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { SettingsScreen } from "@/components/settings/settings-screen";

export default function SettingsPage() {
  return (
    <AppShell>
      {/* useSearchParams (section routing) requires a Suspense boundary. */}
      <Suspense>
        <SettingsScreen />
      </Suspense>
    </AppShell>
  );
}
