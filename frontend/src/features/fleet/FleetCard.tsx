import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { NotReported } from "@/components/NotReported";
import { StatusPill } from "@/components/StatusPill";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { FleetAssetView } from "@/types";
import { formatRelativeTime } from "@/utils/format";

import { HEALTH_TONES } from "./status";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <dt className="shrink-0 text-sm text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-sm font-medium">{children}</dd>
    </div>
  );
}

const ASSET_TYPE_LABELS: Record<FleetAssetView["asset_type"], string> = {
  node: "Node",
  service: "Service",
  agent: "Agent",
  device: "Device",
  sensor: "Sensor",
};

interface FleetCardProps {
  asset: FleetAssetView;
  /** Hardware identity from Host Inventory (nodes only); null = not reported. */
  hardware: string | null;
}

/**
 * One Fleet Registry asset as a keyboard-navigable card (mission §3): the
 * whole card is a real link to the node details, health is color + icon +
 * label, no animations. Uptime is not exposed by the REST API today and is
 * rendered as an honest placeholder (data-source notes in the M004 PR2
 * description).
 */
export function FleetCard({ asset, hardware }: FleetCardProps) {
  const heartbeat = asset.last_heartbeat;
  return (
    <Link
      to={`/fleet/${encodeURIComponent(asset.fleet_id)}`}
      aria-label={`${asset.hostname} (${asset.fleet_id}) — details`}
      className="group rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Card className="h-full transition-colors group-hover:border-muted-foreground/40">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="truncate text-base">{asset.hostname}</CardTitle>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {asset.fleet_id}
                {asset.nickname ? ` · ${asset.nickname}` : ""}
              </p>
            </div>
            <Badge variant="outline" className="shrink-0">
              {ASSET_TYPE_LABELS[asset.asset_type]}
            </Badge>
          </div>
          <StatusPill tone={HEALTH_TONES[asset.health]} label={asset.health} className="text-sm" />
        </CardHeader>
        <CardContent>
          <dl>
            <Row label="Location">{asset.location}</Row>
            <Row label="Environment">{asset.environment}</Row>
            <Row label="Platform">{asset.platform}</Row>
            <Row label="Hardware">
              {hardware ?? <NotReported reason="No host inventory reported for this asset." />}
            </Row>
            <Row label="Uptime">
              <NotReported reason="Uptime is not exposed by the REST API yet (see M004 PR2 data-source notes)." />
            </Row>
            <Row label="Heartbeat">
              {heartbeat ? (
                <time dateTime={heartbeat.timestamp}>
                  {formatRelativeTime(heartbeat.timestamp)}
                </time>
              ) : (
                "Never"
              )}
            </Row>
            <Row label="Collector">
              {heartbeat?.collector_version ?? (
                <NotReported reason="No heartbeat received from this asset yet." />
              )}
            </Row>
          </dl>
        </CardContent>
      </Card>
    </Link>
  );
}
