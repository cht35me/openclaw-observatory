import { TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { isAuthError } from "@/api/client";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
}

/** Inline error panel with retry; auth failures point at Settings instead of retry loops. */
export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const auth = isAuthError(error);
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center"
    >
      <TriangleAlert aria-hidden="true" className="size-6 text-status-warn" />
      <p className="text-sm text-muted-foreground">
        {auth
          ? "The Observatory rejected the API key. Check the key configured in Settings."
          : "Could not load data from the Observatory backend."}
      </p>
      {auth ? (
        <Button asChild variant="outline" size="sm">
          <Link to="/settings">Open Settings</Link>
        </Button>
      ) : (
        onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )
      )}
    </div>
  );
}
