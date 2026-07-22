/** Central query-key vocabulary — invalidation and tests share these. */

export const queryKeys = {
  health: ["health"] as const,
  fleet: ["fleet"] as const,
  fleetAsset: (fleetId: string) => ["fleet", fleetId] as const,
  hostInventory: (fleetId: string) => ["fleet", fleetId, "inventory"] as const,
  dockerStatus: (fleetId: string) => ["fleet", fleetId, "docker-status"] as const,
  missions: ["missions"] as const,
  events: ["events"] as const,
};
