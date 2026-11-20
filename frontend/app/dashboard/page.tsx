"use client";

import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { DashboardContent } from "./_components/dashboard-content";

export default function DashboardPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="state-row">Загрузка обзора…</div>}>
        <DashboardContent />
      </Suspense>
    </AppShell>
  );
}
