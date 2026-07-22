import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { getApiKey, setApiKey } from "@/api/apiKey";
import { isApiRequestError, isAuthError } from "@/api/client";
import { getHealth, probeAuthenticated } from "@/api/endpoints";
import { StatusPill, type StatusTone } from "@/components/StatusPill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface CheckResult {
  tone: StatusTone;
  label: string;
}

interface TestOutcome {
  reachability: CheckResult;
  auth: CheckResult | null;
}

async function runConnectionTest(key: string): Promise<TestOutcome> {
  let reachability: CheckResult;
  try {
    const health = await getHealth();
    reachability = {
      tone: health.status === "ok" ? "ok" : "warn",
      label: `Backend reachable — ${health.status} (${health.version})`,
    };
  } catch {
    return {
      reachability: { tone: "critical", label: "Backend unreachable" },
      auth: null,
    };
  }

  if (!key) {
    return { reachability, auth: { tone: "unknown", label: "No API key to test" } };
  }

  try {
    await probeAuthenticated(key);
    return { reachability, auth: { tone: "ok", label: "API key accepted" } };
  } catch (error) {
    if (isAuthError(error)) {
      return { reachability, auth: { tone: "critical", label: "API key rejected" } };
    }
    const detail =
      isApiRequestError(error) && error.error.kind === "http"
        ? `Authenticated request failed (HTTP ${error.error.status})`
        : "Authenticated request failed";
    return { reachability, auth: { tone: "warn", label: detail } };
  }
}

/**
 * API key entry (docs/frontend-architecture.md §8): a dedicated read-only UI
 * identity issued under SD-017, entered once and kept in localStorage. The
 * connection test probes /health (reachability, unauthenticated) and
 * /api/v1/missions (key validity).
 */
export function ApiKeyForm() {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(() => getApiKey() ?? "");
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [outcome, setOutcome] = useState<TestOutcome | null>(null);

  const handleSave = (event: FormEvent) => {
    event.preventDefault();
    setApiKey(draft.trim() || null);
    setSaved(true);
    // New identity — drop every cached read and refetch with the new key.
    void queryClient.invalidateQueries();
  };

  const handleTest = async () => {
    setTesting(true);
    setOutcome(null);
    try {
      setOutcome(await runConnectionTest(draft.trim()));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>API key</CardTitle>
        <CardDescription>
          Reads from the Observatory REST API require an API key (X-API-Key). Ask the operator for a
          dedicated read-only UI identity; the key is stored only in this browser.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSave} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="api-key">API key</Label>
            <Input
              id="api-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="Paste the UI identity key"
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setSaved(false);
                setOutcome(null);
              }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit">Save key</Button>
            <Button
              type="button"
              variant="outline"
              disabled={testing}
              onClick={() => void handleTest()}
            >
              {testing ? "Testing…" : "Test connection"}
            </Button>
            {saved && (
              <span role="status" className="text-sm text-muted-foreground">
                Saved.
              </span>
            )}
          </div>
          {outcome && (
            <div role="status" className="flex flex-col gap-1.5 text-sm">
              <StatusPill tone={outcome.reachability.tone} label={outcome.reachability.label} />
              {outcome.auth && <StatusPill tone={outcome.auth.tone} label={outcome.auth.label} />}
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
