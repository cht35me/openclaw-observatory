import {
  KeyRound,
  LayoutDashboard,
  Menu,
  ScrollText,
  Server,
  Settings,
  Telescope,
  Workflow,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { OfflineBanner } from "@/components/OfflineBanner";
import { Button } from "@/components/ui/button";
import { useApiKey } from "@/hooks/useApiKey";
import { cn } from "@/utils/cn";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/fleet", label: "Fleet", icon: Server, end: false },
  { to: "/services", label: "Services", icon: Workflow, end: false },
  { to: "/events", label: "Events", icon: ScrollText, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
] as const;

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <ul className="flex flex-col gap-1">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
              )
            }
          >
            <Icon aria-hidden="true" className="size-4 shrink-0" />
            {label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function ApiKeyHint() {
  const apiKey = useApiKey();
  if (apiKey) return null;
  return (
    <NavLink
      to="/settings"
      className="flex items-center gap-2 rounded-md border border-status-warn/40 bg-status-warn/10 px-3 py-2 text-xs text-status-warn"
    >
      <KeyRound aria-hidden="true" className="size-3.5 shrink-0" />
      API key not configured
    </NavLink>
  );
}

/**
 * App shell: persistent sidebar on desktop, topbar + slide-over menu on
 * mobile. Semantic landmarks, keyboard navigable, visible focus states.
 */
export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[14rem_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden border-r md:flex md:flex-col md:gap-6 md:p-4">
        <div className="flex items-center gap-2 px-3 pt-1">
          <Telescope aria-hidden="true" className="size-5 text-primary" />
          <span className="text-sm font-semibold tracking-wide">Observatory</span>
        </div>
        <nav aria-label="Primary" className="flex-1">
          <NavLinks />
        </nav>
        <ApiKeyHint />
      </aside>

      <div className="flex min-w-0 flex-col">
        {/* Mobile topbar */}
        <header className="flex items-center justify-between border-b px-4 py-3 md:hidden">
          <div className="flex items-center gap-2">
            <Telescope aria-hidden="true" className="size-5 text-primary" />
            <span className="text-sm font-semibold tracking-wide">Observatory</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </Button>
        </header>
        {menuOpen && (
          <nav id="mobile-nav" aria-label="Primary" className="border-b p-3 md:hidden">
            <NavLinks onNavigate={() => setMenuOpen(false)} />
            <div className="pt-2">
              <ApiKeyHint />
            </div>
          </nav>
        )}

        <OfflineBanner />

        <main id="main" className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
