import { AppShell, StatePreviewSwitcher } from "@/components/app-shell";
import DesignSystemShowcase from "@/components/design-system-showcase";

export default function DesignSystemPage() {
  return (
    <AppShell>
      <div className="state-row">
        <StatePreviewSwitcher />
      </div>
      <DesignSystemShowcase />
    </AppShell>
  );
}
