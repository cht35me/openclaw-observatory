import type { HostInventoryRecord } from "@/types";
import { formatInstalledMemory } from "@/utils/format";

/** Hardware identity line for a card, e.g. "Raspberry Pi 4 Model B · 4 GB". */
export function hardwareSummary(record: HostInventoryRecord | undefined): string | null {
  const hardware = record?.payload.hardware;
  if (!hardware) return null;
  const parts: string[] = [];
  if (hardware.model) parts.push(hardware.model);
  if (typeof hardware.memory_total_bytes === "number") {
    parts.push(formatInstalledMemory(hardware.memory_total_bytes));
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}
