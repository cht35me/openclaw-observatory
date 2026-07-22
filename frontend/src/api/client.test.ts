/**
 * API client error-path tests (mission Testing & Quality): 401, 5xx,
 * network failure, error normalization, header injection, and the retry
 * policy exercised through a real TanStack QueryClient.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setApiKey } from "./apiKey";
import { apiFetch, ApiRequestError, isAuthError, isRetryableError } from "./client";
import { createQueryClient } from "./queryClient";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("apiFetch error normalization", () => {
  it("normalizes 401 into an http ApiError with the backend detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid API key." }));
    const failure = await apiFetch("/api/v1/fleet").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiRequestError);
    const error = failure as ApiRequestError;
    expect(error.error).toEqual({ kind: "http", status: 401, detail: "Invalid API key." });
    expect(isAuthError(error)).toBe(true);
    expect(isRetryableError(error)).toBe(false);
  });

  it("never copies the API key into normalized errors (threat model §9.2)", async () => {
    setApiKey("UI01-super-secret");
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid API key." }));
    const failure = await apiFetch("/api/v1/fleet").catch((error: unknown) => error);
    const error = failure as ApiRequestError;
    expect(JSON.stringify(error.error)).not.toContain("UI01-super-secret");
    expect(error.message).not.toContain("UI01-super-secret");
  });

  it("normalizes 5xx into a retryable http ApiError", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(503, { detail: "Storage backend unavailable." }));
    const failure = await apiFetch("/health").catch((error: unknown) => error);
    const error = failure as ApiRequestError;
    expect(error.error).toEqual({
      kind: "http",
      status: 503,
      detail: "Storage backend unavailable.",
    });
    expect(isRetryableError(error)).toBe(true);
    expect(isAuthError(error)).toBe(false);
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" }),
    );
    const failure = await apiFetch("/health").catch((error: unknown) => error);
    const error = failure as ApiRequestError;
    expect(error.error).toEqual({ kind: "http", status: 502, detail: "Bad Gateway" });
  });

  it("normalizes fetch rejections into a retryable network ApiError", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const failure = await apiFetch("/health").catch((error: unknown) => error);
    const error = failure as ApiRequestError;
    expect(error.error).toEqual({
      kind: "network",
      detail: "Observatory backend unreachable.",
    });
    expect(isRetryableError(error)).toBe(true);
  });

  it("re-throws deliberate aborts untouched", async () => {
    fetchMock.mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));
    const failure = await apiFetch("/health").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(DOMException);
    expect(isRetryableError(failure)).toBe(false);
  });
});

describe("apiFetch header injection", () => {
  it("sends X-API-Key when a key is stored", async () => {
    setApiKey("UI01-secret");
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await apiFetch("/api/v1/fleet");
    const [, init] = fetchMock.mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-API-Key")).toBe("UI01-secret");
  });

  it("omits X-API-Key when no key is stored", async () => {
    setApiKey(null);
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await apiFetch("/health");
    const [, init] = fetchMock.mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-API-Key")).toBeNull();
  });

  it("prefers an explicit key override (Settings connection test)", async () => {
    setApiKey("stored-key");
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await apiFetch("/api/v1/missions", { apiKey: "candidate-key" });
    const [, init] = fetchMock.mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-API-Key")).toBe("candidate-key");
  });
});

describe("retry policy through TanStack Query", () => {
  it("retries network/5xx failures twice, then succeeds", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(503, { detail: "unavailable" }))
      .mockResolvedValueOnce(jsonResponse(200, { status: "ok" }));
    const queryClient = createQueryClient();
    const data = await queryClient.fetchQuery({
      queryKey: ["retry-success"],
      queryFn: () => apiFetch<{ status: string }>("/health"),
      retryDelay: 0,
    });
    expect(data).toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("gives up after two retries on persistent 5xx", async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, { detail: "boom" }));
    const queryClient = createQueryClient();
    await expect(
      queryClient.fetchQuery({
        queryKey: ["retry-exhausted"],
        queryFn: () => apiFetch("/health"),
        retryDelay: 0,
      }),
    ).rejects.toBeInstanceOf(ApiRequestError);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("never retries a 401", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "Invalid API key." }));
    const queryClient = createQueryClient();
    await expect(
      queryClient.fetchQuery({
        queryKey: ["no-retry-401"],
        queryFn: () => apiFetch("/api/v1/fleet"),
        retryDelay: 0,
      }),
    ).rejects.toBeInstanceOf(ApiRequestError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
