import { PageHeader } from "@/components/PageHeader";
import { ActiveMissionCard, FleetSummaryCard, ObservatoryCard } from "@/features/dashboard/cards";

/** Landing page: cards only, no tables (Mission M004 §2). */
export function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" description="Observatory at a glance." />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ObservatoryCard />
        <ActiveMissionCard />
        <FleetSummaryCard />
      </div>
    </>
  );
}
