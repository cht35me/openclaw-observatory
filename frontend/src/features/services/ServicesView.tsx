import { Info, Workflow } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { NotReported } from "@/components/NotReported";
import { StatusPill } from "@/components/StatusPill";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { HEALTH_TONES } from "@/features/fleet/status";
import { useFleet } from "@/features/fleet/useFleetQueries";
import { useHealth } from "@/features/health/useHealth";
import { formatRelativeTime, formatUptime } from "@/utils/format";

import { deriveServices, type ServiceKind, type ServiceRuntime } from "./useServicesData";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <dt className="shrink-0 text-sm text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-sm font-medium">{children}</dd>
    </div>
  );
}

const TELEMETRY_GAP =
  "Collected as docker_status telemetry, but not exposed by the REST API yet (M004 PR2 data-source notes).";
const UPTIME_GAP =
  "Collector heartbeats carry uptime_seconds, but the registry read model drops it (M004 PR2 data-source notes).";

function ServiceCard({ service }: { service: ServiceRuntime }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="break-words text-base">{service.name}</CardTitle>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{service.subtitle}</p>
          </div>
          <StatusPill
            tone={HEALTH_TONES[service.health]}
            label={service.health}
            className="shrink-0 text-sm"
          />
        </div>
      </CardHeader>
      <CardContent>
        <dl>
          <Row label="Version">
            {service.version ?? <NotReported reason="No version reported yet." />}
          </Row>
          <Row label="Uptime">
            {service.uptimeSeconds !== null ? (
              formatUptime(service.uptimeSeconds)
            ) : (
              <NotReported reason={UPTIME_GAP} />
            )}
          </Row>
          <Row label="Heartbeat">
            {service.heartbeat ? (
              <time dateTime={service.heartbeat.timestamp}>
                {formatRelativeTime(service.heartbeat.timestamp)}
              </time>
            ) : (
              "Never"
            )}
          </Row>
          <Row label="Restarts">
            <NotReported reason={TELEMETRY_GAP} />
          </Row>
          <Row label="CPU">
            <NotReported reason={TELEMETRY_GAP} />
          </Row>
          <Row label="RAM">
            <NotReported reason={TELEMETRY_GAP} />
          </Row>
          <Row label="RX">
            <NotReported reason={TELEMETRY_GAP} />
          </Row>
          <Row label="TX">
            <NotReported reason={TELEMETRY_GAP} />
          </Row>
        </dl>
      </CardContent>
    </Card>
  );
}

const GROUPS: { kind: ServiceKind; heading: string; emptyText: string }[] = [
  { kind: "backend", heading: "Backend", emptyText: "No backend service registered." },
  { kind: "host-collector", heading: "Host collectors", emptyText: "No nodes registered." },
  { kind: "agent-collector", heading: "Agent collectors", emptyText: "No agents registered." },
  {
    kind: "exporter",
    heading: "Exporters",
    emptyText: "No exporters registered in the Fleet Registry.",
  },
];

function ServicesSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" aria-hidden="true">
      {Array.from({ length: 3 }, (_, index) => (
        <Card key={index}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent className="flex flex-col gap-2.5">
            {Array.from({ length: 6 }, (_, row) => (
              <Skeleton key={row} className="h-4 w-full" />
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/** Services runtime view (mission §5): one card per service, grouped by kind. */
export function ServicesView() {
  const fleet = useFleet();
  const health = useHealth();

  if (fleet.isPending) return <ServicesSkeleton />;
  if (fleet.isError) {
    return <ErrorState error={fleet.error} onRetry={() => void fleet.refetch()} />;
  }
  if (fleet.data.length === 0) {
    return (
      <EmptyState
        icon={Workflow}
        title="No services registered"
        description="The Fleet Registry is empty, so there are no services to show yet."
      />
    );
  }

  const services = deriveServices(fleet.data, health.data);

  return (
    <div className="flex flex-col gap-8">
      <aside
        role="note"
        className="flex items-start gap-2 rounded-md border bg-card px-4 py-3 text-sm text-muted-foreground"
      >
        <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        <p>
          Restart count, CPU, RAM, and RX/TX are collected as docker_status telemetry, and collector
          uptime travels in heartbeats — but the REST API does not expose them yet. Those fields
          read “Not reported” until the additive endpoints proposed with M004 PR2 land.
        </p>
      </aside>

      {GROUPS.map((group) => {
        const members = services.filter((service) => service.kind === group.kind);
        return (
          <section key={group.kind} aria-labelledby={`services-${group.kind}`}>
            <h2
              id={`services-${group.kind}`}
              className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground"
            >
              {group.heading}
            </h2>
            {members.length === 0 ? (
              <p className="text-sm text-muted-foreground">{group.emptyText}</p>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {members.map((service) => (
                  <ServiceCard key={service.id} service={service} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
