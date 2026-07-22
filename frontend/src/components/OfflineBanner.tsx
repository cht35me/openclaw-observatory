import { WifiOff } from "lucide-react";

import { isBackendUnreachable, useHealth } from "@/features/health/useHealth";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

import { Button } from "./ui/button";

/**
 * Global, non-blocking offline banner (mission §9): shown when the browser
 * is offline or the backend is unreachable. Cached data stays visible
 * underneath; a manual retry is always available.
 */
export function OfflineBanner() {
  const browserOnline = useOnlineStatus();
  const health = useHealth();

  const backendDown = health.isError && isBackendUnreachable(health.error);
  if (browserOnline && !backendDown) return null;

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-3 border-b border-status-warn/40 bg-status-warn/10 px-4 py-2 text-sm text-status-warn"
    >
      <WifiOff aria-hidden="true" className="size-4 shrink-0" />
      <span>
        {browserOnline
          ? "Observatory backend unreachable — showing cached data."
          : "You are offline — showing cached data."}
      </span>
      <Button
        variant="outline"
        size="sm"
        className="h-7 border-status-warn/40 text-status-warn hover:bg-status-warn/10"
        onClick={() => void health.refetch()}
      >
        Retry
      </Button>
    </div>
  );
}
