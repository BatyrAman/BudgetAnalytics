import { AccountDetailScreen } from "@/components/accounts/account-detail-screen";

export default async function AccountPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccountDetailScreen id={Number(id)} />;
}
