import { GoalDetailScreen } from "@/components/goals/goal-detail-screen";

export default async function GoalPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GoalDetailScreen id={Number(id)} />;
}
