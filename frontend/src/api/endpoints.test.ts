/**
 * Endpoint-definition tests for PR2 (mission Testing & Quality): the Host
 * Inventory path is built and encoded correctly, and its 404 — a *normal*
 * condition meaning "nothing reported yet" — normalizes into a
 * non-retryable http ApiError the UI can branch on.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, isRetryableError } from "./client";
import { getDockerStatus, getFleetAsset, getHostInventory, listEvents } from "./endpoints";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("fleet endpoints", () => {
  it("requests the encoded inventory path for a fleet id", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { fleet_id: "RPSG01", payload: {} }));
    await getHostInventory("RPSG01");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/fleet/RPSG01/inventory");
  });

  it("URL-encodes hostile fleet ids instead of splicing them into the path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));
    await getHostInventory("../evil?x=1");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/fleet/..%2Fevil%3Fx%3D1/inventory");

    fetchMock.mockResolvedValueOnce(jsonResponse(200, {}));
    await getFleetAsset("a b");
    expect(fetchMock.mock.calls[0 + 1]?.[0]).toBe("/api/v1/fleet/a%20b");
  });

  it("normalizes the backend's inventory 404 into a non-retryable ApiError", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { detail: "No host inventory reported for this fleet_id yet." }),
    );
    const failure = await getHostInventory("A001").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiRequestError);
    const error = failure as ApiRequestError;
    expect(error.error).toEqual({
      kind: "http",
      status: 404,
      detail: "No host inventory reported for this fleet_id yet.",
    });
    expect(isRetryableError(error)).toBe(false);
  });
});

describe("events endpoints (M004 PR3)", () => {
  it("requests the bare events path when no params are given", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await listEvents();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/events");
  });

  it("encodes filters and limit as query parameters", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await listEvents({ collectorId: "RPSG 01", eventType: "heartbeat", limit: 50 });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/events?collector_id=RPSG+01&event_type=heartbeat&limit=50",
    );
  });

  it("normalizes the docker-status 404 into a non-retryable ApiError", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { detail: "No docker telemetry reported for this fleet_id yet." }),
    );
    const failure = await getDockerStatus("A001").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiRequestError);
    expect(isRetryableError(failure)).toBe(false);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/fleet/A001/docker-status");
  });
});
