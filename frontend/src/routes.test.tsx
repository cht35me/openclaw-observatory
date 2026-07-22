/**
 * Route smoke tests (mission Testing & Quality): every route in the routing
 * map renders inside the app shell without crashing. Backend calls are
 * stubbed to stay pending — pages must render their own loading/empty UI.
 */
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderRoute } from "@/test/utils";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
});

describe("route smoke tests", () => {
  it("renders the dashboard at /", async () => {
    renderRoute("/");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("renders the fleet page (loading skeletons) at /fleet", async () => {
    renderRoute("/fleet");
    expect(await screen.findByRole("heading", { name: "Fleet" })).toBeInTheDocument();
    // Pending fetch → skeleton cards, no error and no crash.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the node detail page (loading state) at /fleet/:fleetId", async () => {
    renderRoute("/fleet/RPSG01");
    expect(await screen.findByRole("main")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the services page (loading skeletons) at /services", async () => {
    renderRoute("/services");
    expect(await screen.findByRole("heading", { name: "Services" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the events placeholder at /events", async () => {
    renderRoute("/events");
    expect(await screen.findByRole("heading", { name: "Events" })).toBeInTheDocument();
    expect(screen.getByText(/arrives with mission m004 pr3/i)).toBeInTheDocument();
  });

  it("renders settings at /settings", async () => {
    renderRoute("/settings");
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
  });

  it("renders the not-found page for unknown paths", async () => {
    renderRoute("/no-such-page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
