import { ClipboardList } from "lucide-react";
import type { ReactNode } from "react";

import { ErrorState } from "@/components/ErrorState";
import { StatusPill } from "@/components/StatusPill";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { HEALTH_TONES } from "@/features/fleet/status";
import type { HealthStatus } from "@/types";
import { formatUptime } from "@/utils/format";

import { useHealth } from "../health/useHealth";
import {
  selectActiveMission,
  selectObservatoryEnvironment,
  summarizeFleet,
  useFleet,
  useMissions,
} from "./useDashboardData";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{children}</dd>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      <Skeleton className="h-5 w-28" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}

/** Observatory status card: /health plus the deployment environment from the registry. */
export function ObservatoryCard() {
  const health = useHealth();
  const fleet = useFleet();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Observatory</CardTitle>
      </CardHeader>
      <CardContent>
        {health.isPending ? (
          <CardSkeleton />
        ) : health.isError ? (
          <ErrorState error={health.error} onRetry={() => void health.refetch()} />
        ) : (
          <dl>
            <Row label="Status">
              {health.data.status === "ok" ? (
                <StatusPill tone="ok" label="Operational" />
              ) : (
                <StatusPill tone="warn" label="Degraded" />
              )}
            </Row>
            <Row label="Version">{health.data.version}</Row>
            <Row label="Uptime">{formatUptime(health.data.uptime_seconds)}</Row>
            <Row label="Database">
              {health.data.database.connected ? (
                <StatusPill tone="ok" label="Connected" />
              ) : (
                <StatusPill tone="critical" label="Disconnected" />
              )}
            </Row>
            <Row label="Environment">
              {fleet.data ? (selectObservatoryEnvironment(fleet.data) ?? "—") : "—"}
            </Row>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

/** Active mission card: the most recently updated non-completed mission. */
export function ActiveMissionCard() {
  const missions = useMissions();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Active mission</CardTitle>
      </CardHeader>
      <CardContent>
        {missions.isPending ? (
          <CardSkeleton />
        ) : missions.isError ? (
          <ErrorState error={missions.error} onRetry={() => void missions.refetch()} />
        ) : (
          (() => {
            const mission = selectActiveMission(missions.data);
            if (!mission) {
              return (
                <div className="flex flex-col items-center gap-2 py-6 text-center">
                  <ClipboardList aria-hidden="true" className="size-6 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    No mission in flight — all tracked missions are completed.
                  </p>
                </div>
              );
            }
            return (
              <dl>
                <Row label="Mission">{mission.mission_id}</Row>
                <Row label="State">
                  <Badge>{mission.state}</Badge>
                </Row>
                <Row label="Agent">{mission.assigned_agent ?? "—"}</Row>
                <div className="pt-2">
                  <p className="text-sm text-muted-foreground">{mission.title}</p>
                </div>
              </dl>
            );
          })()
        )}
      </CardContent>
    </Card>
  );
}

/** Fleet summary card: asset counts, connectivity, and health breakdown. */
export function FleetSummaryCard() {
  const fleet = useFleet();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Fleet</CardTitle>
      </CardHeader>
      <CardContent>
        {fleet.isPending ? (
          <CardSkeleton />
        ) : fleet.isError ? (
          <ErrorState error={fleet.error} onRetry={() => void fleet.refetch()} />
        ) : fleet.data.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No assets registered yet — seed the Fleet Registry to see them here.
          </p>
        ) : (
          (() => {
            const summary = summarizeFleet(fleet.data);
            return (
              <dl>
                <Row label="Assets">{summary.total}</Row>
                <Row label="Nodes / Services / Agents">
                  {summary.byType.nodes} / {summary.byType.services} / {summary.byType.agents}
                </Row>
                <Row label="Online">
                  {summary.connectivity.online} of {summary.total}
                </Row>
                <div className="flex flex-wrap gap-x-4 gap-y-1.5 pt-2 text-sm">
                  {(Object.keys(HEALTH_TONES) as HealthStatus[])
                    .filter((status) => summary.health[status] > 0)
                    .map((status) => (
                      <StatusPill
                        key={status}
                        tone={HEALTH_TONES[status]}
                        label={`${summary.health[status]} ${status}`}
                      />
                    ))}
                </div>
              </dl>
            );
          })()
        )}
      </CardContent>
    </Card>
  );
}
