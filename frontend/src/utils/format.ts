/** Pure formatting helpers — no React, no I/O. */

/** Format a duration in seconds as a compact human string, e.g. "3d 4h" or "12m". */
export function formatUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.floor(seconds);
  const days = Math.floor(s / 86_400);
  const hours = Math.floor((s % 86_400) / 3_600);
  const minutes = Math.floor((s % 3_600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${s}s`;
}

/** Binary-prefixed byte size, e.g. "57.9 GiB" (matches the /monitor convention). */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "—";
  let size = bytes;
  for (const unit of ["B", "KiB", "MiB", "GiB", "TiB"] as const) {
    if (size < 1024 || unit === "TiB")
      return unit === "B" ? `${size} B` : `${size.toFixed(1)} ${unit}`;
    size /= 1024;
  }
  return "—";
}

/**
 * Installed memory as marketed capacity ("4 GB"): MemTotal is physical RAM
 * minus firmware reservations; rounding to decimal GB recovers module size.
 */
export function formatInstalledMemory(bytes: number | null | undefined): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) return "—";
  const gigabytes = bytes / 1_000_000_000;
  return gigabytes >= 1 ? `${Math.round(gigabytes)} GB` : formatBytes(bytes);
}

/** Percentage with one decimal, e.g. "31.8%". */
export function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value.toFixed(1)}%`;
}

/** Relative time like "42s ago" / "5m ago" for heartbeat freshness. */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "—";
  const deltaSeconds = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 1000));
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  if (deltaSeconds < 3_600) return `${Math.floor(deltaSeconds / 60)}m ago`;
  if (deltaSeconds < 86_400) return `${Math.floor(deltaSeconds / 3_600)}h ago`;
  return `${Math.floor(deltaSeconds / 86_400)}d ago`;
}

/** Relative time for a Unix epoch (seconds), e.g. apt-update freshness. */
export function formatEpochRelative(
  epoch: number | null | undefined,
  now: Date = new Date(),
): string {
  if (typeof epoch !== "number" || !Number.isFinite(epoch)) return "—";
  return formatRelativeTime(new Date(epoch * 1000).toISOString(), now);
}
