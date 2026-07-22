import { ScrollText } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

/** Placeholder — Events timeline lands in M004 PR3. */
export function EventsPage() {
  return (
    <>
      <PageHeader title="Events" description="Recent telemetry across the fleet." />
      <EmptyState
        icon={ScrollText}
        title="Events timeline is on its way"
        description="This page will show a filterable, auto-refreshing timeline of recent events — services, collectors, heartbeats, warnings, and errors. It arrives with Mission M004 PR3."
      />
    </>
  );
}
