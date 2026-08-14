import { DashboardPage } from "@/pages/DashboardPage";

/** `/` lands on the dashboard (onboarding opens as a modal when needed). */
export function HomeRedirect() {
  return <DashboardPage />;
}
