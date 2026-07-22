import { Navigate, useParams } from "react-router-dom";

import { NodeDetailView } from "@/features/inventory/NodeDetailView";

/** Node details (mission §4): registry identity + M003.5 Host Inventory. */
export function NodeDetailPage() {
  const { fleetId } = useParams<{ fleetId: string }>();
  if (!fleetId) return <Navigate to="/fleet" replace />;
  return <NodeDetailView fleetId={fleetId} />;
}
