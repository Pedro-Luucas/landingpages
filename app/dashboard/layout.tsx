import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { DASHBOARD_COOKIE, isDashboardSessionAuthorized } from "@/lib/auth";

export default async function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const store = await cookies();
  if (!isDashboardSessionAuthorized(store.get(DASHBOARD_COOKIE)?.value)) redirect("/dashboard-login");
  return children;
}
