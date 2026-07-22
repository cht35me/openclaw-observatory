/**
 * Honest placeholder for a field the REST API does not (yet) provide.
 * Deliberately plain text — never a fake zero or a hidden row — so gaps in
 * telemetry stay visible to operators (mission §9 meaningful states).
 */
export function NotReported({ reason }: { reason?: string }) {
  return (
    <span className="font-normal text-muted-foreground" title={reason}>
      Not reported
    </span>
  );
}
