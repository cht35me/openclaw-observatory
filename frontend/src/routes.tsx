import type { RouteObject } from "react-router-dom";

import { AppLayout } from "@/layouts/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { EventsPage } from "@/pages/EventsPage";
import { FleetPage } from "@/pages/FleetPage";
import { NodeDetailPage } from "@/pages/NodeDetailPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ServicesPage } from "@/pages/ServicesPage";
import { SettingsPage } from "@/pages/SettingsPage";

/** Routing map (docs/frontend-architecture.md §5). Shared with tests. */
export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "fleet", element: <FleetPage /> },
      { path: "fleet/:fleetId", element: <NodeDetailPage /> },
      { path: "services", element: <ServicesPage /> },
      { path: "events", element: <EventsPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
