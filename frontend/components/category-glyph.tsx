/**
 * Category icons — the single slug → icon map for every screen (categories,
 * operations, budgets, analytics). The backend stores icons as slugs; unknown
 * slugs fall back to a wallet (DESIGN_SYSTEM_SPEC §5).
 */
import {
  Archive,
  BookOpen,
  Briefcase,
  Car,
  Circle,
  CircleHelp,
  Compass,
  CreditCard,
  Ellipsis,
  Film,
  Gift,
  Heart,
  Home,
  Landmark,
  Laptop,
  Layers,
  PawPrint,
  Plus,
  Repeat,
  Shirt,
  ShoppingCart,
  Sparkles,
  Tag,
  Utensils,
  Wallet,
  Wifi,
  type LucideIcon,
} from "lucide-react";

/**
 * Approved icon slugs. The first 16 match the system categories seeded by the
 * backend (note: «Прочие расходы» uses `dots`), the rest are design additions.
 */
export const CATEGORY_ICONS: readonly { slug: string; label: string; Icon: LucideIcon }[] = [
  { slug: "shopping-cart", label: "Корзина", Icon: ShoppingCart },
  { slug: "utensils", label: "Еда", Icon: Utensils },
  { slug: "car", label: "Автомобиль", Icon: Car },
  { slug: "home", label: "Дом", Icon: Home },
  { slug: "wifi", label: "Связь", Icon: Wifi },
  { slug: "heart", label: "Здоровье", Icon: Heart },
  { slug: "shirt", label: "Одежда", Icon: Shirt },
  { slug: "book", label: "Книга", Icon: BookOpen },
  { slug: "film", label: "Кино", Icon: Film },
  { slug: "gift", label: "Подарок", Icon: Gift },
  { slug: "credit-card", label: "Карта", Icon: CreditCard },
  { slug: "dots", label: "Прочее", Icon: Ellipsis },
  { slug: "briefcase", label: "Работа", Icon: Briefcase },
  { slug: "plus", label: "Плюс", Icon: Plus },
  { slug: "repeat", label: "Переводы", Icon: Repeat },
  { slug: "wallet", label: "Кошелёк", Icon: Wallet },
  { slug: "laptop", label: "Ноутбук", Icon: Laptop },
  { slug: "paw-print", label: "Питомцы", Icon: PawPrint },
  { slug: "landmark", label: "Банк", Icon: Landmark },
  { slug: "sparkles", label: "Красота", Icon: Sparkles },
  { slug: "layers", label: "Слои", Icon: Layers },
  { slug: "circle", label: "Круг", Icon: Circle },
  { slug: "tag", label: "Метка", Icon: Tag },
  { slug: "archive", label: "Архив", Icon: Archive },
  { slug: "compass", label: "Путешествия", Icon: Compass },
  { slug: "circle-help", label: "Вопрос", Icon: CircleHelp },
];

/** Legacy/alias slugs seen in older data and the prototype. */
const ALIASES: Record<string, string> = { ellipsis: "dots", "book-open": "book" };

export function categoryIcon(slug: string | undefined): LucideIcon {
  const canonical = slug ? (ALIASES[slug] ?? slug) : undefined;
  return CATEGORY_ICONS.find((item) => item.slug === canonical)?.Icon ?? Wallet;
}
