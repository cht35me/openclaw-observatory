/**
 * Typed REST client (docs/frontend-architecture.md §3/§6).
 *
 * - Same-origin relative URLs: the Vite dev server proxies `/api` and
 *   `/health` to the backend; production serving is same-origin too.
 * - `X-API-Key` header injection from the stored UI identity key (SD-017).
 * - Every failure is normalized to one discriminated `ApiError`, so UI code
 *   switches on `kind`/`status`, never on exception classes.
 * - The client itself never retries: retry policy lives in TanStack Query
 *   (`isRetryableError` below is its predicate).
 */

import { getApiKey } from "./apiKey";

export type ApiError =
  { kind: "http"; status: number; detail: string } | { kind: "network"; detail: string };

export class ApiRequestError extends Error {
  readonly error: ApiError;

  constructor(error: ApiError) {
    super(error.kind === "http" ? `HTTP ${error.status}: ${error.detail}` : error.detail);
    this.name = "ApiRequestError";
    this.error = error;
  }
}

export function isApiRequestError(value: unknown): value is ApiRequestError {
  return value instanceof ApiRequestError;
}

/** Retry predicate for TanStack Query: network failures and 5xx only — a 4xx will not fix itself. */
export function isRetryableError(error: unknown): boolean {
  if (!isApiRequestError(error)) return false;
  return error.error.kind === "network" || error.error.status >= 500;
}

/**
 * True when the error is the backend's 404 — for fleet routes that means an
 * unknown Fleet ID *or* "nothing reported yet" (a normal condition callers
 * branch on, not a failure).
 */
export function isNotFoundError(error: unknown): boolean {
  return isApiRequestError(error) && error.error.kind === "http" && error.error.status === 404;
}

/** True when the error means "the API key is missing, wrong, or not authorized". */
export function isAuthError(error: unknown): boolean {
  return (
    isApiRequestError(error) &&
    error.error.kind === "http" &&
    (error.error.status === 401 || error.error.status === 403)
  );
}

interface ApiFetchOptions {
  signal?: AbortSignal;
  /** Override the stored key (used by the Settings connection test). */
  apiKey?: string;
}

async function parseDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail;
    }
  } catch {
    // Non-JSON error body; fall through to the status text.
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const headers = new Headers({ Accept: "application/json" });
  const key = options.apiKey ?? getApiKey();
  if (key) headers.set("X-API-Key", key);

  let response: Response;
  try {
    response = await fetch(path, { headers, signal: options.signal });
  } catch (cause) {
    // Deliberate aborts (unmount/navigation) are not errors — re-throw so
    // TanStack Query can ignore them instead of surfacing a fake outage.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiRequestError({
      kind: "network",
      detail: "Observatory backend unreachable.",
    });
  }

  if (!response.ok) {
    throw new ApiRequestError({
      kind: "http",
      status: response.status,
      detail: await parseDetail(response),
    });
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiRequestError({
      kind: "network",
      detail: "Observatory backend returned an unreadable response.",
    });
  }
}
