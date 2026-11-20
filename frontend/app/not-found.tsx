import Link from "next/link";
import { AppShell } from "@/components/app-shell";

export default function NotFound() {
  return (
    <AppShell>
      <section className="not-found-page card-surface">
        <span aria-hidden="true">404</span>
        <h2>Раздел не найден</h2>
        <p>Проверьте адрес или вернитесь к обзору финансов.</p>
        <Link className="button primary" href="/dashboard">
          Перейти к обзору
        </Link>
      </section>
    </AppShell>
  );
}
