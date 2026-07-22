import { Server } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { FleetCard } from "./FleetCard";
import { hardwareSummary } from "./hardware";
import { useFleet, useNodeInventories } from "./useFleetQueries";

function FleetCardSkeleton() {
  return (
    <Card aria-hidden="true">
      <CardHeader className="pb-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-4 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}

/** Fleet view: one card per registry asset — cards, not tables (mission §3). */
export function FleetView() {
  const fleet = useFleet();
  const inventories = useNodeInventories(fleet.data);

  if (fleet.isPending) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <FleetCardSkeleton />
        <FleetCardSkeleton />
        <FleetCardSkeleton />
      </div>
    );
  }

  if (fleet.isError) {
    return <ErrorState error={fleet.error} onRetry={() => void fleet.refetch()} />;
  }

  if (fleet.data.length === 0) {
    return (
      <EmptyState
        icon={Server}
        title="No assets registered"
        description="The Fleet Registry is empty. Assets appear here once they are seeded into the backend registry."
      />
    );
  }

  return (
    <ul className="grid list-none grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {fleet.data.map((asset) => (
        <li key={asset.fleet_id} className="min-w-0">
          <FleetCard asset={asset} hardware={hardwareSummary(inventories.get(asset.fleet_id))} />
        </li>
      ))}
    </ul>
  );
}
