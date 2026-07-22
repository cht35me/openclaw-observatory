/** Settings: key persistence and the /health + authed-endpoint connection test. */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getApiKey } from "@/api/apiKey";
import { ApiRequestError } from "@/api/client";
import { healthFixture } from "@/test/fixtures";
import { renderRoute } from "@/test/utils";

vi.mock("@/api/endpoints", () => ({
  getHealth: vi.fn(),
  listFleet: vi.fn(),
  listMissions: vi.fn(),
  getFleetAsset: vi.fn(),
  probeAuthenticated: vi.fn(),
}));

const endpoints = vi.mocked(await import("@/api/endpoints"));

beforeEach(() => {
  endpoints.getHealth.mockResolvedValue(healthFixture);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("settings", () => {
  it("saves the API key to localStorage", async () => {
    const user = userEvent.setup();
    renderRoute("/settings");

    await user.type(screen.getByLabelText("API key"), "UI01-test-key");
    await user.click(screen.getByRole("button", { name: "Save key" }));

    expect(getApiKey()).toBe("UI01-test-key");
    expect(screen.getByText("Saved.")).toBeInTheDocument();
  });

  it("reports reachability and key acceptance on a successful test", async () => {
    endpoints.probeAuthenticated.mockResolvedValue([]);
    const user = userEvent.setup();
    renderRoute("/settings");

    await user.type(screen.getByLabelText("API key"), "UI01-test-key");
    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText(/backend reachable — ok/i)).toBeInTheDocument();
    expect(await screen.findByText("API key accepted")).toBeInTheDocument();
    expect(endpoints.probeAuthenticated).toHaveBeenCalledWith("UI01-test-key");
  });

  it("reports a rejected key distinctly from an unreachable backend", async () => {
    endpoints.probeAuthenticated.mockRejectedValue(
      new ApiRequestError({ kind: "http", status: 401, detail: "Invalid API key." }),
    );
    const user = userEvent.setup();
    renderRoute("/settings");

    await user.type(screen.getByLabelText("API key"), "wrong-key");
    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("API key rejected")).toBeInTheDocument();
  });

  it("reports an unreachable backend without an auth verdict", async () => {
    endpoints.getHealth.mockRejectedValue(
      new ApiRequestError({ kind: "network", detail: "Observatory backend unreachable." }),
    );
    const user = userEvent.setup();
    renderRoute("/settings");

    await user.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("Backend unreachable")).toBeInTheDocument();
    expect(endpoints.probeAuthenticated).not.toHaveBeenCalled();
  });
});
