# SD-015 — Keep the Current Compose Layout During Phase 1

- **Status:** Approved
- **Date:** 2026-07-20
- **Decided by:** Supervisor (Martin)
- **Context:** M002 Gate G2 review — open question 2 in
  [backend/OPEN_QUESTIONS.md](../../backend/OPEN_QUESTIONS.md): the development
  `docker-compose.yml` lives at the repository root (so plain
  `docker compose up` works), while docs/architecture.md §5 places deployment
  compose files under `infra/`.

## Decision

**Keep the current compose layout during Phase 1** — a single development
`docker-compose.yml` resolved by `docker compose up`, with the backend image
built from `backend/Dockerfile`. No restructuring now; *no need to optimize
early.*

## Consequences

- Phase 1 ships with the existing layout: root `docker-compose.yml` +
  `backend/Dockerfile`.
- The repository structure is revisited when additional services exist
  (React frontend, Grafana, collectors). The target shape then becomes:

  ```text
  docker-compose.yml   # root orchestration
  backend/
  frontend/
  collectors/
  deployment/
  ```

- Staging/production compose definitions still arrive with the deployment
  mission (roadmap) and are not part of this decision.

## Related

[architecture.md](../architecture.md#5-proposed-repository-structure) ·
[roadmap.md](../roadmap.md)
