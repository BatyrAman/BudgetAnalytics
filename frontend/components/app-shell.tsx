"use client";

import Link from "next/link";
import { PREVIEW_ENABLED } from "@/lib/preview";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { logout } from "@/lib/api/client";
import { useMe } from "@/lib/api/hooks";
import { SESSION_EXPIRED_EVENT } from "@/lib/api/http";
import { useTheme } from "next-themes";
import {
  Activity,
  Bell,
  BookOpen,
  CircleHelp,
  CreditCard,
  LayoutDashboard,
  ListChecks,
  Menu,
  Moon,
  MoreHorizontal,
  Plus,
  PieChart,
  Settings,
  Sun,
  Target,
  Wallet,
  X,
} from "lucide-react";
import { navigateWithFullReload } from "@/lib/navigation";

const links = [
  { label: "Обзор", href: "/dashboard", icon: LayoutDashboard },
  { label: "Операции", href: "/transactions", icon: Activity },
  { label: "Счета", href: "/accounts", icon: Wallet },
  { label: "Категории", href: "/categories", icon: PieChart },
  { label: "Бюджеты", href: "/budgets", icon: ListChecks },
  { label: "Аналитика", href: "/analytics", icon: BookOpen },
  { label: "Депозиты", href: "/deposits", icon: CreditCard },
  { label: "Цели", href: "/goals", icon: Target },
  { label: "AI-советник", href: "/advisor", icon: CircleHelp },
];
const bottom = [
  { label: "Уведомления", href: "/notifications", icon: Bell },
  { label: "Настройки", href: "/settings", icon: Settings },
];
export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [more, setMore] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { data: me } = useMe();
  const initials = userInitials(me?.full_name);

  useEffect(() => {
    const onExpired = () => {
      const next = `${window.location.pathname}${window.location.search}`;
      navigateWithFullReload(`/login?next=${encodeURIComponent(next)}`);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  async function signOut() {
    setUserMenu(false);
    try {
      await logout();
    } finally {
      navigateWithFullReload("/login");
    }
  }
  const title =
    path === "/design-system"
      ? "Дизайн-система"
      : path.startsWith("/transactions")
        ? "Операции"
        : path.startsWith("/accounts")
          ? "Счета"
          : path.startsWith("/categories")
            ? "Категории"
            : path.startsWith("/budgets")
              ? "Бюджеты"
              : path.startsWith("/analytics")
                ? "Аналитика"
                : path.startsWith("/deposits")
                  ? "Депозиты"
                  : path.startsWith("/goals")
                    ? "Цели"
                    : path.startsWith("/advisor")
                      ? path === "/advisor/report"
                        ? "Финансовый отчёт"
                        : "AI-советник"
                      : (links.concat(bottom).find((l) => l.href === path)?.label ?? "Обзор");
  const description =
    path === "/dashboard"
      ? "Финансовая картина за текущий месяц"
      : path === "/design-system"
        ? "Библиотека компонентов, токенов и состояний интерфейса"
        : path === "/advisor" || path === "/advisor/report"
          ? "Ответы и аналитика по вашим финансам"
          : `Управляйте разделом «${title.toLowerCase()}»`;
  const navItem = (item: (typeof links)[number], compact = false) => (
    <Link
      key={item.href}
      title={compact ? item.label : undefined}
      href={item.href}
      className={`nav-link ${path === item.href || (item.href === "/transactions" && path.startsWith("/transactions")) || (item.href === "/advisor" && path.startsWith("/advisor")) ? "active" : ""} ${compact ? "compact" : ""}`}
    >
      <item.icon size={19} />
      <span>{item.label}</span>
    </Link>
  );
  return (
    <div className="app-frame">
      <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""}`}>
        <Link href="/dashboard" className="brand-lockup">
          <span className="brand-mark">
            <Wallet size={20} />
          </span>
          {!collapsed && (
            <span>
              Budget<span className="brand-light">Analytics</span>
            </span>
          )}
        </Link>
        
        <nav className="side-nav">{links.map((item) => navItem(item, collapsed))}</nav>
        <div className="sidebar-bottom">
          {bottom.map((item) => (
            <Link
              key={item.href}
              title={collapsed ? item.label : undefined}
              href={item.href}
              className={`nav-link ${path === item.href ? "active" : ""} ${collapsed ? "compact" : ""}`}
            >
              <item.icon size={19} />
              <span>{item.label}</span>
              {item.href === "/notifications" && !collapsed && (
                <small className="soon-label">Скоро</small>
              )}
            </Link>
          ))}
          <div className="user-card">
            <span className="avatar" aria-hidden="true">
              {initials}
            </span>
            {!collapsed && (
              <span className="user-copy">
                <b>{me?.full_name ?? "…"}</b>
                <small>{me?.email ?? ""}</small>
              </span>
            )}
          </div>
          <button
            className="collapse-button"
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
          >
            {collapsed ? (
              <Menu size={18} />
            ) : (
              <>
                <Menu size={18} /> Свернуть меню
              </>
            )}
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-mark">
              <Wallet size={18} />
            </span>
            BudgetAnalytics
          </div>
          <div className="page-title">
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          <div className="header-actions">
            {PREVIEW_ENABLED && <span className="demo-pill">Режим разработки</span>}
            <label className="theme-control">
              <Sun size={15} />
              <select
                aria-label="Тема оформления"
                value={theme ?? "light"}
                onChange={(e) => setTheme(e.target.value)}
              >
                <option value="light">Светлая</option>
                <option value="dark">Тёмная</option>
                <option value="system">Системная</option>
              </select>
              <Moon size={14} />
            </label>
            <div className="header-user">
              <button
                className="avatar header-avatar"
                aria-label="Меню пользователя"
                aria-expanded={userMenu}
                onClick={() => setUserMenu(!userMenu)}
              >
                {initials}
              </button>
              {userMenu && (
                <div className="user-menu overlay-shadow" role="menu">
                  <strong>{me?.full_name ?? "…"}</strong>
                  <small>{me?.email ?? ""}</small>
                  <Link role="menuitem" href="/settings" onClick={() => setUserMenu(false)}>
                    Настройки
                  </Link>
                  <button role="menuitem" type="button" onClick={() => void signOut()}>
                    Выйти
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="main-content">{children}</main>
      </div>
      <nav className="bottom-nav">
        <Link href="/dashboard" className={path === "/dashboard" ? "selected" : ""}>
          <LayoutDashboard />
          <span>Обзор</span>
        </Link>
        <Link href="/transactions">
          <Activity />
          <span>Операции</span>
        </Link>
        <button
          className="mobile-add"
          onClick={() => router.push("/transactions?new=1")}
          aria-label="Добавить операцию"
        >
          <Plus />
        </button>
        <Link href="/analytics">
          <PieChart />
          <span>Аналитика</span>
        </Link>
        <button onClick={() => setMore(true)}>
          <MoreHorizontal />
          <span>Ещё</span>
        </button>
      </nav>
      {more && (
        <div className="sheet-backdrop" onClick={() => setMore(false)}>
          <section
            className="more-sheet"
            onClick={(e) => e.stopPropagation()}
            aria-label="Дополнительная навигация"
          >
            <div className="sheet-heading">
              <b>Разделы</b>
              <button onClick={() => setMore(false)} aria-label="Закрыть">
                <X />
              </button>
            </div>
            {links.slice(2).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMore(false)}
                className="more-link"
              >
                <item.icon size={18} />
                {item.label}
              </Link>
            ))}
            {bottom.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMore(false)}
                className="more-link"
              >
                <item.icon size={18} />
                {item.label}
              </Link>
            ))}
          </section>
        </div>
      )}
    </div>
  );
}
export function StatePreviewSwitcher() {
  if (!PREVIEW_ENABLED) return null;
  return (
    <Suspense fallback={<span className="state-switcher">Демо: состояние — Обычное</span>}>
      <StatePreviewControl />
    </Suspense>
  );
}
function StatePreviewControl() {
  const params = useSearchParams();
  const router = useRouter();
  const state = params.get("state") ?? "default";
  return (
    <label className="state-switcher">
      Демо: состояние
      <select
        aria-label="Демо: состояние"
        value={state}
        onChange={(e) => {
          const p = new URLSearchParams(params.toString());
          if (e.target.value === "default") p.delete("state");
          else p.set("state", e.target.value);
          router.replace(`${location.pathname}${p.size ? "?" + p.toString() : ""}`);
        }}
      >
        <option value="default">Обычное</option>
        <option value="loading">Загрузка</option>
        <option value="empty">Пусто</option>
        <option value="error">Ошибка</option>
      </select>
    </label>
  );
}

function userInitials(name: string | undefined): string {
  if (!name) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
