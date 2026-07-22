import { PageHeader } from "@/components/PageHeader";
import { FleetView } from "@/features/fleet/FleetView";

/** Fleet view (mission §3): one card per registry asset, cards not tables. */
export function FleetPage() {
  return (
    <>
      <PageHeader title="Fleet" description="Every registered node, agent, and service." />
      <FleetView />
    </>
  );
}
