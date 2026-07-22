/** Central query-key vocabulary — invalidation and tests share these. */

export const queryKeys = {
  health: ["health"] as const,
  fleet: ["fleet"] as const,
  fleetAsset: (fleetId: string) => ["fleet", fleetId] as const,
  missions: ["missions"] as const,
};
