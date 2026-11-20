import { Bell, Clock3, FileCheck2, Target, Wallet } from "lucide-react";

/**
 * Design-review examples for the planned notifications list. Rendered only when
 * PREVIEW_ENABLED (development) and only after the «Демо: макет списка» switch is on.
 * Every card is labelled «Пример»; nothing is stored.
 */
export type ExampleNotification = {
  id: string;
  title: string;
  preview: string;
  body: string;
  /** Relative description instead of a fake absolute date. */
  when: string;
  entityLabel: string;
  href: string;
  Icon: typeof Bell;
};

export const EXAMPLE_NOTIFICATIONS: ExampleNotification[] = [
  {
    id: "budget",
    title: "Превышение бюджета",
    preview: "Кафе и рестораны · лимит превышен",
    body: "Расходы по категории «Кафе и рестораны» превысили месячный бюджет. Проверьте операции и план расходов.",
    when: "Пример: сегодня",
    entityLabel: "Открыть бюджеты",
    href: "/budgets",
    Icon: Wallet,
  },
  {
    id: "deposit",
    title: "Скоро окончание депозита",
    preview: "Депозит завершится через 30 дней",
    body: "До плановой даты окончания депозита осталось 30 дней. Сверьте условия продления с вашим банком.",
    when: "Пример: сегодня",
    entityLabel: "Открыть депозиты",
    href: "/deposits",
    Icon: Clock3,
  },
  {
    id: "goal",
    title: "Цель достигнута",
    preview: "«Отпуск в Турции» · собрана плановая сумма",
    body: "Цель «Отпуск в Турции» достигла плановой суммы.",
    when: "Пример: вчера",
    entityLabel: "Открыть цели",
    href: "/goals",
    Icon: Target,
  },
  {
    id: "import",
    title: "Импорт завершён",
    preview: "Выписка импортирована",
    body: "Пример уведомления об успешном завершении импорта банковской выписки.",
    when: "Пример: вчера",
    entityLabel: "Открыть историю импорта",
    href: "/transactions/import/history",
    Icon: FileCheck2,
  },
];
