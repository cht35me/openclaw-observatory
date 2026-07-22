import { Server } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

/** Placeholder — Fleet cards land in M004 PR2. */
export function FleetPage() {
  return (
    <>
      <PageHeader title="Fleet" description="Every registered node, agent, and service." />
      <EmptyState
        icon={Server}
        title="Fleet view is on its way"
        description="This page will show a card per fleet asset — hostname, location, environment, platform, uptime, heartbeat, and health. It arrives with Mission M004 PR2."
      />
    </>
  );
}
