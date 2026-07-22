import { ArrowLeft, Boxes, HardDrive, ListTree } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { isNotFoundError } from "@/api/client";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { NotReported } from "@/components/NotReported";
import { StatusPill } from "@/components/StatusPill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CONNECTIVITY_LABELS, CONNECTIVITY_TONES, HEALTH_TONES } from "@/features/fleet/status";
import { useFleetAsset, useHostInventory } from "@/features/fleet/useFleetQueries";
import type { FleetAssetView, HostInventoryPayload, StorageDevice } from "@/types";
import {
  formatBytes,
  formatEpochRelative,
  formatInstalledMemory,
  formatPercent,
  formatRelativeTime,
} from "@/utils/format";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <dt className="shrink-0 text-sm text-muted-foreground">{label}</dt>
      <dd className="break-words text-right text-sm font-medium">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function SectionNotReported({ what }: { what: string }) {
  return <p className="py-2 text-sm text-muted-foreground">{what} not reported by this host.</p>;
}

function value(text: string | number | null | undefined): ReactNode {
  return text === null || text === undefined || text === "" ? (
    <span className="text-muted-foreground">—</span>
  ) : (
    text
  );
}

// ---------------------------------------------------------------- sections

function IdentitySection({ asset }: { asset: FleetAssetView }) {
  const heartbeat = asset.last_heartbeat;
  return (
    <Section title="Identity">
      <dl>
        <Row label="Fleet ID">{asset.fleet_id}</Row>
        <Row label="Role">{value(asset.role)}</Row>
        <Row label="Platform">{value(asset.platform)}</Row>
        <Row label="Software">{value(asset.software_version)}</Row>
        <Row label="Environment">{value(asset.environment)}</Row>
        <Row label="Lifecycle">{value(asset.status)}</Row>
        <Row label="Location">{value(asset.location)}</Row>
        <Row label="Heartbeat">
          {heartbeat ? (
            <time dateTime={heartbeat.timestamp}>{formatRelativeTime(heartbeat.timestamp)}</time>
          ) : (
            "Never"
          )}
        </Row>
        <Row label="Collector">
          {heartbeat?.collector_version ? (
            `${heartbeat.collector_version}${heartbeat.collector_type ? ` (${heartbeat.collector_type})` : ""}`
          ) : (
            <NotReported reason="No heartbeat received from this asset yet." />
          )}
        </Row>
        {asset.host_fleet_id && (
          <Row label="Runs on">
            <Link
              className="underline underline-offset-4 hover:text-foreground"
              to={`/fleet/${encodeURIComponent(asset.host_fleet_id)}`}
            >
              {asset.host_fleet_id}
            </Link>
          </Row>
        )}
      </dl>
    </Section>
  );
}

function HardwareSection({ payload }: { payload: HostInventoryPayload }) {
  const hardware = payload.hardware;
  if (!hardware) {
    return (
      <Section title="Hardware">
        <SectionNotReported what="Hardware identity" />
      </Section>
    );
  }
  const cpu = [
    hardware.cpu_model,
    hardware.cpu_architecture,
    hardware.cpu_cores ? `${hardware.cpu_cores} cores` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Section title="Hardware">
      <dl>
        <Row label="Manufacturer">{value(hardware.manufacturer)}</Row>
        <Row label="Model">
          {hardware.model
            ? `${hardware.model}${hardware.revision ? ` (rev ${hardware.revision})` : ""}`
            : value(null)}
        </Row>
        <Row label="CPU">{value(cpu)}</Row>
        <Row label="Installed memory">{formatInstalledMemory(hardware.memory_total_bytes)}</Row>
        <Row label="Serial">{value(hardware.serial)}</Row>
      </dl>
    </Section>
  );
}

function OperatingSystemSection({ payload }: { payload: HostInventoryPayload }) {
  const os = payload.os;
  if (!os) {
    return (
      <Section title="Operating System">
        <SectionNotReported what="Operating-system identity" />
      </Section>
    );
  }
  return (
    <Section title="Operating System">
      <dl>
        <Row label="OS">{value(os.pretty_name ?? os.name)}</Row>
        <Row label="Release">
          {value(os.release ? `${os.release}${os.version_id ? ` (${os.version_id})` : ""} ` : null)}
        </Row>
        <Row label="Kernel">{value(os.kernel)}</Row>
        <Row label="Hostname">{value(os.hostname)}</Row>
      </dl>
    </Section>
  );
}

function StorageEntry({ device }: { device: StorageDevice }) {
  return (
    <li className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{device.name ?? device.device ?? "Disk"}</span>
        {device.type && <Badge variant="outline">{device.type}</Badge>}
        {device.transport && <Badge variant="outline">{device.transport}</Badge>}
      </div>
      <dl className="mt-2">
        <Row label="Mount">{value(device.mount)}</Row>
        <Row label="Device">{value(device.device)}</Row>
        <Row label="Brand">{value(device.brand)}</Row>
        <Row label="Filesystem">{value(device.filesystem)}</Row>
        <Row label="Capacity">{formatBytes(device.capacity_bytes)}</Row>
        <Row label="Used">
          {typeof device.used_bytes === "number" || typeof device.used_percent === "number"
            ? `${formatBytes(device.used_bytes)} (${formatPercent(device.used_percent)})`
            : "—"}
        </Row>
        <Row label="Free">{formatBytes(device.free_bytes)}</Row>
      </dl>
    </li>
  );
}

function StorageSection({ payload }: { payload: HostInventoryPayload }) {
  const devices = payload.storage ?? [];
  return (
    <Section title="Storage">
      {devices.length === 0 ? (
        <SectionNotReported what="Storage inventory" />
      ) : (
        <ul className="grid list-none grid-cols-1 gap-3 sm:grid-cols-2">
          {devices.map((device, index) => (
            <StorageEntry
              key={`${device.device ?? "disk"}-${device.mount ?? index}`}
              device={device}
            />
          ))}
        </ul>
      )}
    </Section>
  );
}

function InterfacesSection({ payload }: { payload: HostInventoryPayload }) {
  const network = payload.network;
  const interfaces = network?.interfaces ?? [];
  if (!network || interfaces.length === 0) {
    return (
      <Section title="Interfaces">
        <SectionNotReported what="Network interfaces" />
      </Section>
    );
  }
  const route = network.default_route;
  return (
    <Section title="Interfaces">
      <ul className="flex list-none flex-col divide-y">
        {interfaces.map((iface, index) => (
          <li
            key={iface.name ?? index}
            className="flex flex-wrap items-center justify-between gap-2 py-2"
          >
            <span className="text-sm font-medium">{iface.name ?? "—"}</span>
            <span className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">{iface.ipv4 ?? "no address"}</span>
              <StatusPill
                tone={
                  iface.link_state === "up"
                    ? "ok"
                    : iface.link_state === "down"
                      ? "offline"
                      : "unknown"
                }
                label={(iface.link_state ?? "unknown").toUpperCase()}
                className="text-xs"
              />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm text-muted-foreground">
        {route?.gateway || route?.interface
          ? `Default route: ${route.gateway ?? "—"} via ${route.interface ?? "—"}`
          : "No default route reported."}
      </p>
    </Section>
  );
}

function MaintenanceSection({ payload }: { payload: HostInventoryPayload }) {
  const maintenance = payload.maintenance;
  if (!maintenance) {
    return (
      <Section title="Maintenance">
        <SectionNotReported what="Maintenance status" />
      </Section>
    );
  }
  return (
    <Section title="Maintenance">
      <dl>
        <Row label="Last apt update">{formatEpochRelative(maintenance.last_apt_update_epoch)}</Row>
        <Row label="Last apt upgrade">{value(maintenance.last_apt_upgrade)}</Row>
        <Row label="Last full-upgrade">{value(maintenance.last_apt_full_upgrade)}</Row>
        <Row label="Updates available">
          {typeof maintenance.updates_available === "number" ? (
            <StatusPill
              tone={maintenance.updates_available > 0 ? "warn" : "ok"}
              label={String(maintenance.updates_available)}
            />
          ) : (
            "—"
          )}
        </Row>
        <Row label="Reboot required">
          {maintenance.reboot_required === true ? (
            <StatusPill tone="warn" label="Required" />
          ) : maintenance.reboot_required === false ? (
            <StatusPill tone="ok" label="No" />
          ) : (
            "—"
          )}
        </Row>
      </dl>
    </Section>
  );
}

function RunningServicesSection() {
  return (
    <Section title="Running Services">
      <p className="py-2 text-sm text-muted-foreground">
        Not reported — the host collector does not observe systemd services yet, and no REST
        endpoint carries them. An additive collector + endpoint proposal is in the M004 PR2
        data-source notes.
      </p>
    </Section>
  );
}

function DockerSection() {
  return (
    <Section title="Docker Containers">
      <p className="py-2 text-sm text-muted-foreground">
        Container telemetry is collected (docker_status events feed the /monitor page), but the REST
        API does not expose it yet. Rendering waits on the additive endpoint proposed in the M004
        PR2 data-source notes.
      </p>
    </Section>
  );
}

function DetailSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2" aria-hidden="true">
      {Array.from({ length: 4 }, (_, index) => (
        <Card key={index}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent className="flex flex-col gap-2.5">
            {Array.from({ length: 5 }, (_, row) => (
              <Skeleton key={row} className="h-4 w-full" />
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- view

/**
 * Node details: registry identity + the M003.5 Host Inventory sections.
 * Renders gracefully when inventory is missing (agents/services never report
 * it) or partial (fail-soft collector sections).
 */
export function NodeDetailView({ fleetId }: { fleetId: string }) {
  const asset = useFleetAsset(fleetId);
  const inventory = useHostInventory(fleetId);

  if (asset.isPending) {
    return (
      <>
        <header className="mb-6">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="mt-2 h-4 w-32" />
        </header>
        <DetailSkeleton />
      </>
    );
  }

  if (asset.isError) {
    if (isNotFoundError(asset.error)) {
      return (
        <EmptyState
          icon={HardDrive}
          title="Unknown fleet asset"
          description={`No asset with Fleet ID “${fleetId}” exists in the Fleet Registry.`}
        >
          <Button asChild variant="outline" size="sm">
            <Link to="/fleet">
              <ArrowLeft aria-hidden="true" /> Back to Fleet
            </Link>
          </Button>
        </EmptyState>
      );
    }
    return <ErrorState error={asset.error} onRetry={() => void asset.refetch()} />;
  }

  const view = asset.data;
  const record = inventory.data;

  return (
    <>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold">{view.hostname}</h1>
          <StatusPill tone={HEALTH_TONES[view.health]} label={view.health} className="text-sm" />
          <StatusPill
            tone={CONNECTIVITY_TONES[view.connectivity]}
            label={CONNECTIVITY_LABELS[view.connectivity]}
            className="text-sm"
          />
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {view.fleet_id}
          {view.nickname ? ` · ${view.nickname}` : ""} · {view.location}
          {record && (
            <>
              {" · inventory reported "}
              <time dateTime={record.reported_at}>{formatRelativeTime(record.reported_at)}</time>
            </>
          )}
        </p>
      </header>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <IdentitySection asset={view} />

        {inventory.isPending ? (
          <Card aria-hidden="true">
            <CardHeader className="pb-3">
              <Skeleton className="h-5 w-32" />
            </CardHeader>
            <CardContent className="flex flex-col gap-2.5">
              {Array.from({ length: 5 }, (_, row) => (
                <Skeleton key={row} className="h-4 w-full" />
              ))}
            </CardContent>
          </Card>
        ) : inventory.isError && !isNotFoundError(inventory.error) ? (
          <ErrorState error={inventory.error} onRetry={() => void inventory.refetch()} />
        ) : record ? (
          <>
            <HardwareSection payload={record.payload} />
            <OperatingSystemSection payload={record.payload} />
            <MaintenanceSection payload={record.payload} />
            <div className="lg:col-span-2">
              <StorageSection payload={record.payload} />
            </div>
            <InterfacesSection payload={record.payload} />
            <RunningServicesSection />
            <DockerSection />
          </>
        ) : (
          <div className="lg:col-span-1">
            <EmptyState
              icon={view.asset_type === "node" ? ListTree : Boxes}
              title="No host inventory"
              description={
                view.asset_type === "node"
                  ? "This node has not reported a host_inventory event yet. Inventory arrives with the host collector's first report."
                  : "Only nodes running the host collector report host inventory. This asset is a " +
                    `${view.asset_type}${view.host_fleet_id ? ` running on ${view.host_fleet_id}` : ""}.`
              }
            >
              {view.host_fleet_id && (
                <Button asChild variant="outline" size="sm">
                  <Link to={`/fleet/${encodeURIComponent(view.host_fleet_id)}`}>
                    View host {view.host_fleet_id}
                  </Link>
                </Button>
              )}
            </EmptyState>
          </div>
        )}
      </div>
    </>
  );
}
