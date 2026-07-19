# Deployment Strategy — OpenClaw Observatory

Status: **Strategy only. Nothing is deployed during M001.**

## 1. Deployment Lifecycle Overview

```text
Develop (Raspberry Pi SG01)
   │  feature branch → Pull Request
   ▼
GitHub (review, human approval, merge to main)
   │  tested artifact / tagged release
   ▼
VPS Staging (soak, verification)
   │  human approval
   ▼
VPS Production (monitored, backed up, rollback-ready)
   ▲
   └── Distributed collectors connect from remote hosts over the tailnet
```

1. **Development on Raspberry Pi SG01:** agents develop on feature branches in local
   clones; local runs and tests only — the Pi never serves production traffic.
2. **GitHub feature branches and Pull Requests:** every change reaches `main` only
   through a reviewed PR ([AGENTS.md](../AGENTS.md)).
3. **Human review and merge:** supervisor approval is the release gate; merges are
   performed by or under the authority of a human ([MISSION.md](../MISSION.md)).
4. **Testing:** unit/integration tests run before PR (locally at first; CI in a later
   phase per [roadmap.md](roadmap.md)). A change without stated validation does not ship.
5. **VPS staging deployment:** merged code deploys first to a staging instance on the
   VPS (separate containers/ports/data), soaks with real-but-noncritical telemetry, and
   is verified against a checklist.
6. **Production deployment on VPS:** after explicit human approval, the same artifact
   (not a rebuild) is promoted to production.
7. **Distributed collectors:** remote hosts (RPSG01 first, later hosts as commissioned)
   run collectors that push to production over the tailnet with per-collector
   credentials.
8. **Monitoring and rollback:** production is monitored from deploy time; a documented,
   rehearsed rollback path exists for every release.

## 2. Environment Separation

| Environment | Where | Purpose | Data |
| --- | --- | --- | --- |
| Development | Pi SG01 (and future dev hosts) | build and test changes | synthetic/local |
| Staging | VPS (isolated containers) | pre-production verification | non-critical/mirrored |
| Production | VPS | the real Observatory | fleet data, backed up |

- Environments never share databases, credentials, or tokens.
- Staging is configured identically to production except size, secrets, and endpoints.
- Environment-specific behavior comes from configuration, never from code branches.

## 3. Configuration Management

- All configuration in version control as `*.example` templates with placeholders;
  real values injected per environment (env vars / host-local files).
- One configuration mechanism across environments; differences are values, not shapes.
- Configuration changes to production follow the same review path as code.

## 4. Secrets Management

- Secrets are never in Git, images, or logs ([security.md](security.md) §5).
- Injected at deploy time via environment variables or host-local files with tight
  permissions; a dedicated secret manager is a future upgrade if secret count grows.
- Separate secrets per environment; staging compromise must not expose production.
- Rotation procedures documented alongside each credential's issuance record.

## 5. Container-Based Deployment

**Recommendation:** Docker (or compatible) containers orchestrated with Compose on the
VPS.

- **Why:** reproducible artifacts, clean separation of staging/production on one VPS,
  restart policies for free, easy rollback by image tag, and the fleet's scale does not
  justify Kubernetes-class orchestration.
- **Trade-offs:** image hygiene and update discipline become part of operations.
- **Alternatives:** systemd services from release tarballs (simpler runtime, weaker
  isolation/reproducibility); Kubernetes/Nomad (unjustified operational weight at this
  scale); Podman as a drop-in Docker alternative (worth evaluating at implementation).

Images: official, version-pinned bases; built from the repository; tagged with release
version + commit; staging and production run the *same image*.

## 6. Backups

- Automated scheduled backups of the production database and configuration; at least one
  copy stored off the VPS.
- Backup restore is **exercised** on staging at Phase 4 and periodically thereafter
  ([roadmap.md](roadmap.md)) — an untested backup is a hope, not a backup.
- Retention: enough history to recover from slow-burn corruption, not just crashes
  (e.g., daily for 14 days + weekly for 8 weeks as a starting point; finalize at Phase 4).

## 7. Updates

- **Application:** release-tagged, staged-then-promoted, never edited in place.
- **OS/runtime:** unattended security patches where safe (host OS); container base
  images refreshed deliberately via rebuild PRs.
- **Dependencies:** upgraded through reviewed PRs with pinned versions
  ([security.md](security.md) §8).
- Update windows are irrelevant at current scale but recorded in logs for correlation.

## 8. Rollback

- Every production deploy records: previous image tag, database schema version, config
  version.
- Rollback = redeploy previous image tag; database migrations must be
  backward-compatible one step or ship with a tested down-migration
  ([ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) §10).
- If rollback is impossible for a given change, that fact is declared in the PR and
  requires explicit supervisor acknowledgment before deploy.

## 9. Health Checks, Logging, and Metrics

- **Health:** liveness/readiness endpoints consumed by container restart policies and
  external monitoring; the deploy process verifies health before declaring success.
- **Logging:** structured JSON logs with rotation/retention; secret-free by policy;
  shipped/aggregated in a later phase if needed.
- **Metrics:** the Observatory exposes its own `/metrics` (Prometheus-compatible) from
  MVP — self-observability is a launch feature, not an afterthought
  ([vision.md](vision.md)).

## 10. Network Security

- All Observatory traffic (collectors, dashboard, SSH) rides the private tailnet
  (Tailscale or equivalent); **no Observatory ports are exposed publicly.**
- VPS firewall is default-deny on the public interface; SSH is key-only and
  tailnet-preferred.
- Per-collector credentials + tailnet identity provide two independent authentication
  layers for ingestion.
- Details and alternatives (WireGuard, mTLS): [security.md](security.md) §6 and
  [architecture.md](architecture.md) §2.3.

## 11. Production Hardening Checklist (to satisfy before/at Phase 4)

- [ ] Default-deny firewall verified on public interface
- [ ] SSH: key-only, no root login, tailnet-restricted where feasible
- [ ] Automatic security updates on host OS
- [ ] Containers run as non-root with minimal images
- [ ] Secrets present only in runtime environment, never in images or Git
- [ ] Per-collector tokens issued and individually revocable
- [ ] Backups running and restore rehearsed
- [ ] Health checks wired to restart policy
- [ ] Structured logging with retention configured
- [ ] `/metrics` exposed and scraped/watched
- [ ] Rollback rehearsed on staging
- [ ] Incident-response runbook reachable and current ([security.md](security.md) §12)

---

Related: [architecture.md](architecture.md) · [security.md](security.md) ·
[roadmap.md](roadmap.md) · [requirements.md](requirements.md)
