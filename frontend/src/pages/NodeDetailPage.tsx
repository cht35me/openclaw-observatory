import { HardDrive } from "lucide-react";
import { useParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";

/** Placeholder — Node details (Host Inventory sections) land in M004 PR2. */
export function NodeDetailPage() {
  const { fleetId } = useParams<{ fleetId: string }>();
  return (
    <>
      <PageHeader title={fleetId ?? "Node"} description="Node details and host inventory." />
      <EmptyState
        icon={HardDrive}
        title="Node details are on their way"
        description="This page will show the M003.5 Host Inventory for this node — hardware, storage, operating system, interfaces, maintenance, running services, and Docker containers. It arrives with Mission M004 PR2."
      />
    </>
  );
}
