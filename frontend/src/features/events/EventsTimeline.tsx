import {
  Activity,
  Bot,
  CircleCheck,
  CircleOff,
  ClipboardList,
  Container,
  HardDrive,
  HeartPulse,
  Power,
  ScrollText,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { StatusPill } from "@/components/StatusPill";
import { Skeleton } from "@/components/ui/skeleton";
import type { ObservatoryEvent } from "@/types";
import { cn } from "@/utils/cn";
import { formatRelativeTime } from "@/utils/format";

import {
  EVENT_FILTERS,
  eventDetail,
  eventSeverity,
  eventTitle,
  filterEvents,
  type EventFilter,
  type EventSeverity,
} from "./model";
import { useEvents } from "./useEvents";

const TYPE_ICONS: Record<string, LucideIcon> = {
  heartbeat: HeartPulse,
  system_metrics: Activity,
  docker_status: Container,
  agent_status: Bot,
  host_inventory: HardDrive,
  mission_update: ClipboardList,
  service_start: Power,
  asset_offline: CircleOff,
  asset_online: CircleCheck,
};

/** Restrained severity colour — always paired with an icon and, for
 * warning/error, an explicit text label (never colour alone). */
const SEVERITY_ICON_CLASSES: Record<EventSeverity, string> = {
  info: "text-muted-foreground",
  ok: "text-status-ok",
  warning: "text-status-warn",
  error: "text-status-critical",
};

function FilterChips({
  active,
  onToggle,
  onClear,
}: {
  active: ReadonlySet<EventFilter>;
  onToggle: (filter: EventFilter) => void;
  onClear: () => void;
}) {
  const chipClass = (pressed: boolean) =>
    cn(
      "rounded-full border px-3 py-1 text-sm transition-colors",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      pressed
        ? "border-primary bg-primary text-primary-foreground"
        : "bg-card text-muted-foreground hover:text-foreground",
    );
  return (
    <div role="group" aria-label="Filter events" className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        aria-pressed={active.size === 0}
        className={chipClass(active.size === 0)}
        onClick={onClear}
      >
        All
      </button>
      {EVENT_FILTERS.map((filter) => (
        <button
          key={filter.id}
          type="button"
          aria-pressed={active.has(filter.id)}
          className={chipClass(active.has(filter.id))}
          onClick={() => onToggle(filter.id)}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}

function TimelineItem({ event, isLast }: { event: ObservatoryEvent; isLast: boolean }) {
  const severity = eventSeverity(event);
  const Icon = TYPE_ICONS[event.event_type] ?? Zap;
  const detail = eventDetail(event);
  const timestamp = new Date(event.timestamp);
  const absolute = Number.isNaN(timestamp.getTime()) ? event.timestamp : timestamp.toLocaleString();

  return (
    <li className="relative flex gap-4 pb-6">
      {!isLast && (
        <span aria-hidden="true" className="absolute left-[15px] top-8 h-full w-px bg-border" />
      )}
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border bg-card",
          SEVERITY_ICON_CLASSES[severity],
        )}
      >
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="text-sm font-medium">{eventTitle(event)}</p>
          {severity === "warning" && <StatusPill tone="warn" label="Warning" className="text-xs" />}
          {severity === "error" && <StatusPill tone="critical" label="Error" className="text-xs" />}
          <time
            dateTime={event.timestamp}
            title={absolute}
            className="ml-auto shrink-0 text-xs text-muted-foreground"
          >
            {formatRelativeTime(event.timestamp)}
          </time>
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          <span className="font-medium text-foreground/70">{event.collector_id}</span>
          {detail && <> · {detail}</>}
        </p>
      </div>
    </li>
  );
}

function TimelineSkeleton() {
  return (
    <div className="flex flex-col gap-5" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="flex items-start gap-4">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Events timeline (mission §6): filter chips + auto-refreshing feed. */
export function EventsTimeline() {
  const events = useEvents();
  const [active, setActive] = useState<ReadonlySet<EventFilter>>(new Set());

  const toggle = (filter: EventFilter) => {
    setActive((current) => {
      const next = new Set(current);
      if (next.has(filter)) next.delete(filter);
      else next.add(filter);
      return next;
    });
  };

  if (events.isPending) return <TimelineSkeleton />;
  if (events.isError) {
    return <ErrorState error={events.error} onRetry={() => void events.refetch()} />;
  }

  const visible = filterEvents(events.data, active);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterChips active={active} onToggle={toggle} onClear={() => setActive(new Set())} />
        <p className="text-xs text-muted-foreground">Auto-refreshes every 15 s</p>
      </div>

      {events.data.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No events yet"
          description="The event stream is empty. Events appear here as soon as collectors report telemetry."
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="Nothing matches these filters"
          description="No recent event matches the selected filters. Clear them to see the full timeline."
        />
      ) : (
        <ol aria-label="Event timeline">
          {visible.map((event, index) => (
            <TimelineItem key={event.id} event={event} isLast={index === visible.length - 1} />
          ))}
        </ol>
      )}
    </div>
  );
}
