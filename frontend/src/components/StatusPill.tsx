import { CircleCheck, CircleHelp, CircleOff, OctagonAlert, TriangleAlert } from "lucide-react";

import { cn } from "@/utils/cn";

export type StatusTone = "ok" | "warn" | "critical" | "offline" | "unknown";

const TONE_CLASSES: Record<StatusTone, string> = {
  ok: "text-status-ok",
  warn: "text-status-warn",
  critical: "text-status-critical",
  offline: "text-status-offline",
  unknown: "text-status-unknown",
};

const TONE_ICONS: Record<StatusTone, typeof CircleCheck> = {
  ok: CircleCheck,
  warn: TriangleAlert,
  critical: OctagonAlert,
  offline: CircleOff,
  unknown: CircleHelp,
};

interface StatusPillProps {
  tone: StatusTone;
  label: string;
  className?: string;
}

/**
 * Restrained status indicator: muted color + icon + text label — never color
 * alone (accessibility requirement), never animated (mission §3).
 */
export function StatusPill({ tone, label, className }: StatusPillProps) {
  const Icon = TONE_ICONS[tone];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 font-medium", TONE_CLASSES[tone], className)}
    >
      <Icon aria-hidden="true" className="size-4 shrink-0" />
      <span>{label}</span>
    </span>
  );
}
