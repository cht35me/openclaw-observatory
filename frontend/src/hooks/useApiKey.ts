import { useSyncExternalStore } from "react";

import { getApiKey, subscribeApiKey } from "@/api/apiKey";

/** Reactive view of the stored API key (null when not configured). */
export function useApiKey(): string | null {
  return useSyncExternalStore(subscribeApiKey, getApiKey);
}
