import { PageHeader } from "@/components/PageHeader";
import { EventsTimeline } from "@/features/events/EventsTimeline";

/** Events timeline (Mission M004 §6): filterable, auto-refreshing feed. */
export function EventsPage() {
  return (
    <>
      <PageHeader title="Events" description="Recent telemetry across the fleet." />
      <EventsTimeline />
    </>
  );
}
