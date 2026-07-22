# Frontend Architecture — Observatory Operations Console (Mission M004)

- **Status:** Living document — written before implementation (Principles 1 & 2)
- **Mission:** M004 — Observatory Visibility & Frontend (Phase 3)
- **Owner:** A001 (agent) · Martin (supervisor)
- **Scope of this document:** the whole M004 frontend; PR1 implements the
  foundation (scaffold, theme, layout, routing, API client, dashboard shell).

The Observatory frontend is an **operational control console**, not an
analytics dashboard. Visual simplicity beats information density; it must
never resemble Grafana. It complements — and never replaces — the
server-rendered `/monitor` emergency panel (SD-020).

## 1. Tech Stack and Rationale

| Choice | Rationale | Rejected alternative |
| --- | --- | --- |
| **Vite** | Fast dev server + esbuild/Rollup production builds; first-class TS + React templates; tiny config surface. | CRA (deprecated), Next.js (SSR is pointless for a LAN SPA and adds a Node runtime to the Pi). |
| **React 18 + TypeScript (strict)** | Mission-mandated; strict mode catches contract drift against backend models at compile time. | — |
| **React Router v7 (library mode)** | Client-side routing for `/fleet/:fleetId` etc.; data APIs unused — TanStack Query owns data. | TanStack Router (younger, no added value here). |
| **TanStack Query v5** | Caching, background refresh, retry with backoff, offline detection — precisely the mission's §9/Performance requirements, without hand-rolled state. | Redux (explicitly excluded), SWR (weaker retry/invalidations). |
| **TailwindCSS v3 + shadcn/ui** | Mission-mandated. shadcn/ui components are vendored source (Radix primitives + Tailwind), so we own and can audit every line — no opaque UI dependency. Tailwind v3 chosen over v4 because shadcn/ui tooling and its CSS-variable theming recipe are stable on v3. | Component libraries (MUI et al.: heavy, themed wrong, harder to keep "not Grafana"). |
| **Vitest + React Testing Library** | Native Vite integration; jsdom environment; same transform pipeline as the build — no Babel/Jest config drift. | Jest. |

No Redux. No CSS-in-JS runtime. No charting library in PR1 (and none planned:
the console is status-first, not graphs-first).

## 2. Folder Structure

Per the mission specification, under `frontend/src/`:

```text
frontend/
├── src/
│   ├── api/          # REST client, endpoint definitions, query keys
│   ├── components/   # reusable presentation-only UI (incl. components/ui = shadcn/ui)
│   ├── features/     # business logic per domain: dashboard/ fleet/ inventory/ services/ events/ settings/
│   ├── hooks/        # shared React hooks (useApiKey, useOnlineStatus, …)
│   ├── layouts/      # app shell: sidebar/topbar, responsive chrome
│   ├── pages/        # route-level components (thin: compose features)
│   ├── types/        # TypeScript mirrors of backend pydantic models
│   ├── utils/        # pure helpers (formatting, duration, bytes)
│   ├── App.tsx       # router + providers
│   ├── main.tsx      # entry point
│   └── index.css     # Tailwind layers + theme CSS variables
├── index.html
├── vite.config.ts    # dev proxy → 127.0.0.1:8000, vitest config
└── …tooling configs
```

Rules:

- **Business logic lives in `features/`** (hooks that combine queries, derive
  status, map domain → view models).
- **`components/` stays presentation-only** wherever practical: props in,
  DOM out; no fetching, no query hooks.
- **`pages/` are thin**: route wiring + composition of feature components.
- **`types/` mirrors the backend** (`backend/app/models/*.py`,
  `backend/app/api/health.py`) field-for-field. When a pydantic model
  changes, the mirror changes in the same PR (Principle 2).

## 3. Data Flow

```text
component → feature hook → useQuery(queryKey, api/ fetcher) → typed fetch → backend REST
                                    │
                          TanStack Query cache
                (stale-while-revalidate, retry, polling)
```

- **All server state** goes through TanStack Query. No server data in React
  state, no global store.
- **Query keys** are centralized in `api/queryKeys.ts` (e.g. `['fleet']`,
  `['fleet', fleetId]`, `['health']`, `['missions']`) so invalidation and
  tests share one vocabulary.
- **Cached data renders immediately** while fresh data loads
  (`staleTime` below refetch interval ⇒ instant navigation, background
  refresh).
- The API client itself never retries; **retry policy belongs to TanStack
  Query** (single place, visible in devtools, testable). 4xx errors are not
  retried (a 401 will not fix itself); network errors and 5xx retry up to 2
  times with exponential backoff.

### Polling intervals (matched to operational value)

| Data | Interval | Why |
| --- | --- | --- |
| `/health` | 30 s | Backend/DB status changes matter quickly, payload is tiny. |
| `/api/v1/fleet` | 30 s | Heartbeat cadence is 60 s; 30 s keeps connectivity fresh without hammering the Pi. |
| `/api/v1/fleet/{id}` + inventory | 60 s (PR2) | Inventory changes slowly. |
| Events timeline | 15 s (PR3) | Auto-refresh requirement; the most "live" view. |
| `/api/v1/missions` | 60 s | Mission state changes are infrequent. |

Polling pauses when the tab is hidden (`refetchIntervalInBackground:
false`, Query default) — avoids pointless load on the Pi.

## 4. Theming — Dark First

- **Class-based dark mode** (`darkMode: "class"`), `<html class="dark">` set
  by default in `index.html`. Light theme remains possible later by removing
  the class; no code change required.
- **Semantic CSS variables** (shadcn/ui convention): `--background`,
  `--foreground`, `--card`, `--muted`, `--border`, `--primary`,
  `--destructive`, plus Observatory status tokens `--status-ok`,
  `--status-warn`, `--status-critical`, `--status-offline`,
  `--status-unknown`. Components reference tokens, never raw colors.
- **Restrained palette:** near-black neutral surfaces, one accent, muted
  status hues. Status is always communicated as **color + text label or
  icon** — never color alone (accessibility requirement). **No animations**
  on status indicators; only unobtrusive skeleton pulses while loading.
- Readable contrast in dark theme (target WCAG AA for text).

## 5. Routing Map

| Path | Page | PR |
| --- | --- | --- |
| `/` | Dashboard — Observatory status, version, environment, DB, active mission, fleet summary. Cards only, no tables. | **PR1 (working)** |
| `/fleet` | Fleet view — node cards | PR1 stub → PR2 |
| `/fleet/:fleetId` | Node details — Host Inventory sections | PR1 stub → PR2 |
| `/services` | Services runtime view | PR1 stub → PR2 |
| `/events` | Events timeline with filters + auto-refresh | PR1 stub → PR3 |
| `/settings` | API key entry + connection test | **PR1 (working)** |
| `*` | Not-found page | PR1 |

Stubs are meaningful empty states (what the page will show and which PR
delivers it), not blank screens. Layout: persistent sidebar on desktop,
collapsing to a topbar + slide-over menu on mobile; fully keyboard
navigable with visible focus rings; semantic landmarks (`<nav>`, `<main>`,
`<header>`).

## 6. Error and Offline Strategy

- **Error normalization:** the API client maps every failure to one
  discriminated `ApiError` type — `{ kind: 'http', status, detail }` (detail
  from FastAPI's `{"detail": …}` body when present) or `{ kind: 'network' }`
  — so UI code switches on `kind`/`status`, never on exception classes.
- **401/403 →** inline "check your API key" state linking to Settings (no
  silent retry loops).
- **Network failure / backend down →** a global, non-blocking **offline
  banner** (driven by query error state + `navigator.onLine`), cached data
  stays visible with a "stale" hint, manual retry button always available.
- **Loading →** skeleton cards matching final layout (no spinners jumping the
  page around).
- **Empty →** meaningful empty states ("No missions tracked yet"), never
  blank panels.
- Query retry: 2 retries with backoff for network/5xx; none for 4xx.

## 7. Proposal (a): Serving Model — **Proposed — Gate review at PR1**

**Development:** Vite dev server proxies `/api` and `/health` to
`http://127.0.0.1:8000` (backend on loopback). Same-origin in the browser ⇒
no CORS anywhere.

**Production (proposal, implemented in PR3, not now):** the FastAPI backend
mounts the built SPA via `StaticFiles` (additive change only — e.g.
`app.mount` of `frontend/dist` at `/ui` or `/`, with SPA-fallback to
`index.html`). Rationale:

- **Same-origin** with the API ⇒ zero CORS configuration, no extra headers,
  no preflight traffic on the Pi.
- **Zero new processes/ports** — matches SD-020's reasoning for `/monitor`:
  the backend already sits behind the network boundary
  (loopback/tailnet-only, SD-003); the SPA inherits exactly that exposure.
- **Alternative considered:** nginx/Caddy in front — rejected at current
  fleet size (new service, new config surface, no benefit until TLS or
  multi-host serving is needed; reversible later).
- Backend change is **additive** (mission §8) and deferred to PR3 so PR1
  stays zero-backend-change. Until then the frontend runs via `vite dev`
  or `vite preview` on the LAN.

**Mount design (supervisor gate requirements, binding for the PR3
implementation):**

- **Routing precedence is preserved:** `/api/*`, `/health`, `/metrics`,
  `/monitor`, and `/docs`/`/openapi.json` are registered API routes and
  always win; the SPA mount only ever serves paths no API route claims.
- **No blanket SPA fallback.** Asset requests (`/assets/*`, `/favicon.svg`,
  anything with a file extension) that don't exist return **404** — a
  missing asset must never silently deliver `index.html`. The SPA
  `index.html` fallback applies only to extension-less, non-API navigation
  paths (`/fleet/RPSG01`, `/settings`, …). Unknown `/api/...` paths keep
  returning the backend's own 404, never the SPA.
- **Frontend is optional at runtime:** the mount is conditional on
  `frontend/dist/` existing. The backend test suite (and any deployment
  without a built frontend) must remain fully runnable and green with no
  `dist/` present — CI enforces this implicitly because backend jobs never
  build the frontend.

## 8. Proposal (b): Browser Auth — **Proposed — Gate review at PR1**

**No auth redesign** (explicitly out of scope). Reuse SD-017 exactly:

- The operator adds one **dedicated named UI identity** to the backend's
  existing `API_KEYS` config, e.g. `UI01:<random-key>` (key → one Fleet
  identity, individually revocable — security.md §2).
- The key is entered **once** in the frontend Settings screen, kept in
  `localStorage`, and sent as `X-API-Key` on every REST read — identical to
  collectors. `/health` stays unauthenticated (SD-013) and doubles as the
  reachability probe; Settings also verifies the key against an authed
  endpoint (`/api/v1/missions`).

**What the UI identity is — and is not (verified against
`backend/app/auth.py` and the v1 routes, supervisor gate requirement):**
the backend has a single `require_collector` dependency guarding *both* the
read endpoints and `POST /api/v1/events`. Authorization today is
*all-authenticated-identities-may-read*, and any identity may also ingest
events — restricted by SD-017 to its **own** `collector_id`. `UI01` is
therefore **not a read-only credential**: it is a *dedicated named identity
for audit and individual revocation*. A leaked UI key could read fleet data
and submit telemetry **as `UI01`** (never as another asset). Per-role
read-only enforcement arrives with the RBAC milestone (architecture §2.8).

**Additive hardening option (proposal only — no backend change in PR1):**
an optional read-only marker per identity (e.g. a `READ_ONLY_IDS` setting
listing identities, or an `API_KEYS` entry suffix), enforced by one additive
check in the ingestion route (`403` when the authenticated subject is
marked read-only). Small, additive, and forward-compatible with RBAC; could
land in PR3 if the supervisor wants it before RBAC.

- **Trade-off (explicit, Principle 14):** `localStorage` is readable by any
  JS on the origin. Said plainly: **stealing this key does not just grant
  reads — it grants the ability to ingest forged telemetry into the event
  stream, attributed to `UI01`** (never to any other asset, per SD-017
  identity binding). Accepted because exposure is bounded by the
  tailnet/loopback network boundary (SD-003), forged events are
  identifiable and auditable by their `UI01` provenance, the key is
  individually revocable, and the controls in §9 below hold. Alternatives
  (session cookie + login endpoint, or proxy-injected key) require backend
  auth changes — out of scope.
- When RBAC arrives, `UI01` becomes a read-only role holder with no further
  frontend change.

## 9. localStorage Threat Model — Controls (all hold in the implementation)

The stored key's primary risk is exfiltration by JavaScript running on the
origin, or accidental leakage through logs and URLs. Controls, each of which
is true of the shipped code and enforced by review/CI:

1. **Zero external code or assets.** No CDN scripts, no external fonts
   (system font stack), no analytics, no third-party requests of any kind.
   Everything is bundled by Vite and self-hosted; the only network calls the
   app makes are same-origin `/health` and `/api/v1/*`. This is the main
   XSS-surface reducer: no foreign origin can inject code.
2. **The key never appears in URLs, query strings, logs, or error
   surfaces.** It travels exclusively in the `X-API-Key` request header.
   Error normalization builds `ApiError` from the response status/body
   only — request headers are never copied into errors, telemetry, or
   console output (regression-tested in `client.test.ts`).
3. **Dependencies are locked.** `package-lock.json` is committed and CI
   installs with `npm ci` — no floating resolutions; supply-chain drift
   requires a reviewed lockfile diff.
4. **Operator can forget the key.** Settings has an explicit “Forget key”
   action that removes it from `localStorage` and clears the TanStack Query
   cache (no authenticated payloads linger in memory beyond the page
   session).

## 10. Testing and Quality Gates

- **TypeScript strict** (`strict: true`, plus `noUncheckedIndexedAccess`),
  `tsc --noEmit` clean.
- **ESLint** (typescript-eslint + react-hooks) clean; **Prettier** check
  clean.
- **Vitest + RTL:** route smoke tests (every route renders), API client
  error-path tests (401, 5xx, network failure, retry/normalization),
  dashboard rendering test with mocked queries.
- **CI:** dedicated frontend job (Node 22 — matches host runtime v22.x):
  `npm ci`, lint, format check, typecheck, tests, production build. Existing
  backend/collector jobs untouched.
- **Performance:** initial usable load < 2 s on Pi LAN. Levers: no charting
  libs, code-split routes when PR2/PR3 grow, gzip/precompressed assets at
  serve time, bundle size reported in every PR.

## 11. Out of Scope (unchanged from mission)

No Bitaxe dashboards, no Grafana replacement, no historical analytics, no
editing/remote administration, no authentication redesign, no OpenClaw
controls, no node configuration. The `/monitor` page remains untouched.
