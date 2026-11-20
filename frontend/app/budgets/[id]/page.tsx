import { BudgetDetailScreen } from "@/components/budgets/budget-detail-screen";

export default async function BudgetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BudgetDetailScreen id={Number(id)} />;
}
