# Dokploy Migration Design

**Date:** 2026-07-05
**Status:** Draft
**Author:** Architecture brainstorm (user + assistant)

## Goal

Replace manual Docker Compose + Caddy + GitHub Actions SSH-deploy stack with Dokploy-managed PaaS. Single VPS (Hetzner 176.9.0.156, 8 CPU / 62 GB RAM). Zero-downtime migration. 20+ services, 15+ subdomains, full data preservation.

## Non-Goals

- Multi-server / cluster setup (single VPS only)
- Switching CI provider (GitHub Actions stays)
- Replacing Prometheus / monitoring stack
- Changing container images or runtime
- Migrating PostHog self-hosted (already using PostHog Cloud)
- Migrating Vast.ai GPU server (external, not on VPS)

## Architecture

### Before

```
GitHub Actions
  ├─ CI (typecheck, lint, test, coverage)
  └─ CD (build → push GHCR → SSH deploy.sh)
       └─ VPS /opt/skatelab/
            └─ compose.prod.yaml
                 ├─ backend, frontend, worker-heavy, worker-fast, prometheus

VPS /opt/infra/
  ├─ compose.yaml
  │   ├─ Caddy (:80/:443, 15+ subdomains)
  │   ├─ Postgres 17, Valkey, ClickHouse
  │   ├─ RustFS, 9router
  │   └─ miniflux, rsshub, searxng, ntfy, mosquitto,
  │       qbittorrent, baikal, openviking, mirofish, vless-sub
  └─ Caddyfile
```

### After

```
GitHub Actions
  ├─ CI (typecheck, lint, test, coverage) — unchanged
  └─ CD (build → push GHCR) — no SSH deploy
       └─ GHCR images: :latest + :$sha

Dokploy (VPS 176.9.0.156)
  ├─ Traefik (:80/:443, Cloudflare DNS challenge, auto-TLS)
  ├─ Project: skatelab
  │   ├─ App: backend (ghcr.io/.../skatelab-backend:latest)
  │   ├─ App: frontend (ghcr.io/.../skatelab-frontend:latest)
  │   ├─ App: worker-heavy (ghcr.io/.../skatelab-arq-worker:latest)
  │   ├─ App: worker-fast
  │   └─ App: prometheus
  └─ Project: infra
      ├─ DB: Postgres 17
      ├─ DB: Valkey
      ├─ DB: ClickHouse
      ├─ App: RustFS
      ├─ App: 9router
      ├─ App: miniflux
      ├─ App: rsshub
      ├─ App: searxng
      ├─ App: ntfy
      ├─ App: mosquitto
      ├─ App: qbittorrent
      ├─ App: baikal
      ├─ App: openviking
      ├─ App: mirofish
      └─ App: vless-sub
```

### CI/CD Split

| Concern | Before | After |
|---------|--------|-------|
| typecheck / lint / test / coverage | Actions | Actions (unchanged) |
| Build images | Actions (Blacksmith) | Actions (Blacksmith, unchanged) |
| Push to GHCR | Actions | Actions (unchanged) |
| Deploy to VPS | Actions SSH + deploy.sh | Dokploy watchtower auto-pull |
| Rollback | Manual `docker tag` + `docker compose up` | Dokploy UI dropdown |
| Logs | `ssh` + `docker logs` | Dokploy UI |
| Secrets | `.env` file on VPS | Dokploy secrets + env |
| Health checks | `deploy.sh` curl loop | Traefik + Dokploy built-in |

## Domain Migration (Caddyfile → Traefik)

Traefik labels in Dokploy service config replace Caddyfile blocks. Middlewares replicate Caddy behavior:

| Caddy feature | Traefik equivalent |
|---------------|-------------------|
| `tls { dns cloudflare }` | Traefik Cloudflare plugin (built-in to Dokploy). **Must be DNS, not HTTP** — wildcards require DNS challenge. |
| `header Strict-Transport-Security ...` | `Headers` middleware (label) |
| `header X-Frame-Options DENY` | Same |
| `header -permissions-policy ...` | `CustomResponseHeaders` middleware |
| `health_uri /v1/health` | Traefik health check (Dokploy UI) |
| `flush_interval -1` (SSE) | Traefik transport `flushInterval: -1` — **validate parity in Phase 1** with real SSE stream test |
| `read_timeout 300s` | Traefik transport `respondingTimeouts.readTimeout` |
| `respond 404` catch-all | Traefik `defaultRule` + 404 service |
| ACME cert storage | Caddy uses `~/.local/share/caddy/`. Traefik uses `acme.json`. **Import existing Caddy certs to avoid LE rate limits (BLOCKER).** |

15+ subdomain routes переносятся one-to-one.

## Phased Migration

### Phase 1 — Bootstrap + warm-start (week 1, overlaps with Phase 2)

**Goal:** Dokploy running, DB containers warm-started, no prod impact.

- Install Dokploy on VPS via official script
- Caddy stays on :80/:443 (current state). Dokploy Traefik learns routes later (Phase 4).
- Dokploy UI on :18080 via VPN only (AmneziaWG subnet 10.99.0.0/24). iptables rule restricts external access.
- Create empty projects `skatelab`, `infra`
- **Network connectivity test (BLOCKER fix):** deploy hello-world, verify Caddy can reach it via `docker network connect infra_app_network <dokploy-container>`. NOT `host.docker.internal` — fails on Linux Docker.
- **SSE/streaming test:** stream SSE endpoint through Dokploy's Traefik, verify `flushInterval: -1` works. If UI doesn't expose, document raw label workaround.
- **TLS cert handoff test:** request cert for non-prod subdomain (e.g., `test.skatelab.ru`), validate Cloudflare DNS challenge + cert issuance.
- **DB warm-start (parallel):** provision Postgres 17, Valkey, ClickHouse in Dokploy project `infra` (idle or seeded with test data). Saves 1-2 days in Phase 3.
- **RustFS background sync (parallel):** provision new RustFS container, start `aws s3 sync` from old bucket. Runs nightly until Phase 3 cutover. Cutover window shrinks to seconds.
- **Image pre-pull (parallel):** `docker pull` all GHCR images on VPS so first deploys start instantly.

**Pass criteria:**
- Dokploy UI loads on `http://10.99.0.1:18080` (via VPN)
- Hello-world app deploys, returns 200
- Caddy can reach Dokploy container by service name through shared network
- SSE stream not buffered
- Test subdomain gets valid TLS cert
- DBs provisioned, idle, ready for Phase 3 data restore
- RustFS sync started, no errors
- Old stack untouched, zero user-visible changes

**Rollback:** `docker compose down dokploy`, port freed. Old stack unaffected. DB containers drained in Phase 5.

### Phase 2 — Migrate SkateLab apps (week 1-2, overlap with Phase 1)

**Goal:** backend, frontend, workers, prometheus running in Dokploy.

- Create 5 services in Dokploy project `skatelab` **in parallel**:
  - backend: image `ghcr.io/.../skatelab-backend`, port 8000
  - frontend: image `ghcr.io/.../skatelab-frontend`, port 3000
  - worker-heavy: image `ghcr.io/.../skatelab-arq-worker`, command `arq app.worker.HeavyWorkerSettings`
  - worker-fast: same image, command `arq app.worker.FastWorkerSettings`
  - prometheus: image `prom/prometheus:v3.3.0`, port 9090
- **Worker queue isolation (BLOCKER fix):** new workers consume from Valkey DB 4 (or queue name prefix). Old workers drain DB 3 during cutover. Switch backend enqueue target atomically with Caddyfile backend change.
- **Network connectivity:** join Dokploy containers to existing `infra_app_network` via `docker network connect` (NOT `host.docker.internal` — fails on Linux Docker). Phase 1 test confirms Caddy reaches Dokploy container by service name through connected network.
- Env vars: copy from current `.env`. Connect to existing Postgres + Valkey + RustFS via shared network.
- Update Caddyfile: change backend target from `backend:8000` to `<dokploy-service-name>:8000` (resolvable via shared network).
- **Canary validation:** add temporary Caddyfile blocks for `api-new.skatelab.ru` and `www-new.skatelab.ru` pointing to Dokploy containers. Smoke-test on canary URLs before main cutover.
- Cutover via Caddy reload.
- Monitor 24h. **Automated health-check polling** (no fixed waits) — exits 0 when `/v1/health`, `/`, worker queue depth all pass within timeout (default 2 min).

**Pass criteria:**
- Login flow works (canary + main)
- Video upload + analysis works
- Worker queue processes jobs (Valkey db 4 for new, db 3 drained for old)
- Error rate < 1%, latency p95 unchanged
- Prometheus scrapes updated targets (compose service names → Dokploy service names in `prometheus.yml`)

**Rollback:** Caddyfile env switch back to old compose targets. Caddy reload. < 1 min cutover.

### Phase 3 — Migrate DB + infra services (week 2-3, overlap with Phase 2)

**Goal:** All DBs and non-SkateLab apps in Dokploy.

- **DB warm-start (already running from Phase 1):** Postgres 17, Valkey, ClickHouse containers provisioned and idle. Phase 1 overlap saves 1-2 days.
- **Parallel backups:** `pg_dumpall`, `valkey-cli BGSAVE`, ClickHouse `BACKUP DATABASE` run simultaneously (single script with background jobs).
- **Postgres replication (BLOCKER fix):** use `pglogical` to keep new Dokploy Postgres in sync during migration. Old DB stays read-write. At cutover: stop old writes briefly, wait for replication catch-up, switch backend `DATABASE_URL` atomically. **No data loss.**
- Restore data to Dokploy-managed DBs in parallel with SkateLab app validation.
- **Background RustFS sync (BLOCKER fix):** start `aws s3 sync` from old to new bucket in Phase 1. Run incremental sync nightly until Phase 3 cutover. Cutover window shrinks to seconds.
- **Batch service migration (5 parallel batches):**
  - Batch A (network layer): RustFS, 9router — stateless, parallel
  - Batch B (utility web): miniflux, baikal, rsshub, searxng, ntfy, mosquitto, qbittorrent, vless-sub — zero interdependencies, parallel
  - Batch C (mirofish): requires Neo4j dependency
  - Batch D (openviking): requires 9router
  - Batch E (cleanup): depends on A-D completion
- **MiroFish pre-step:** push `localhost/mirofish-local:latest` to GHCR as `ghcr.io/.../mirofish-local:latest` (Dokploy doesn't support `pull_policy: never`).
- **ClickHouse verification:** confirm ClickHouse actually deployed. If not, remove from migration scope.
- Update Caddyfile per batch (one reload per batch, not per service).
- Validate each batch individually.

**Pass criteria:**
- All 15+ subdomains respond correctly
- Data integrity: row counts match pre-migration, S3 bucket inventory matches
- All credentials unchanged (Caddy env vars point to new service names)
- No data drift between old and new (Postgres replication caught all writes)

**Rollback:** Promote old Postgres as primary, revert Caddyfile targets.

### Phase 4 — Switch Traefik (week 4)

**Goal:** Traefik (in Dokploy) handles all routing. Caddy no-op kept as fallback.

- **Config pre-written in Phase 3:** all 15+ Traefik routes + middlewares drafted while services still on Caddy. Phase 4 = DNS cutover + monitoring, not config work.
- Configure Traefik in Dokploy with all 15+ domain routes.
- Replicate Caddy middlewares:
  - HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
  - Cloudflare DNS challenge (Traefik plugin, not HTTP — wildcards need DNS)
  - SSE flush interval: validate `flushInterval: -1` in Phase 1 with real SSE stream test. If Dokploy UI doesn't expose, use raw Traefik dynamic config label.
  - Read/write timeouts
- **TLS cert handoff (BLOCKER fix):** Let's Encrypt rate-limits duplicate certs (5/week). Options:
  - Import existing Caddy ACME certs into Traefik store
  - Use single Cloudflare wildcard cert (`*.skatelab.ru`) instead of per-subdomain
  - Validate chosen approach in Phase 1 with non-prod subdomain.
- Test on low-traffic subdomain first (e.g., `rss.skatelab.ru`).
- **Dokploy compose downtime fallback:** Dokploy issue #2497 confirms 5-10s downtime on recreate. Keep Caddy no-op container running until Dokploy zero-downtime compose support lands.
- Cutover:
  - Caddyfile: `api.skatelab.ru { respond 204 }` (drop the route)
  - Traefik takes over via DNS resolution

**Pass criteria:**
- All 15+ subdomains work via Traefik
- TLS certs valid (auto-renew works)
- Security headers present (`curl -I` check)
- SSE streams not buffered (analysis endpoint test)
- 72h monitoring: no cert renewal failures, no middleware missing

**Rollback:** Caddyfile restore from `/opt/infra/.archive/Caddyfile.phase4`. Caddy starts handling routes again.

### Phase 5 — Cleanup (week 4-5)

- Delete services from `/opt/infra/compose.yaml` (now empty)
- Move `infra/deploy.sh`, `infra/compose.prod.yaml` to `/opt/skatelab/.archive/`
- Update `.github/workflows/deploy.yml`:
  - Remove `deploy-files` and `deploy` jobs
  - **CI critical path optimization:** remove `needs:ci` from image build jobs. Keep final deploy job gated on both `ci` and `build-images`. Drops critical path from ~17-25 min to ~7-10 min.
  - **Matrix builds:** collapse `build-frontend`, `build-backend`, `build-arq-worker` into single matrix job
  - **GHA cache:** add `cache-from type=gha` to all image build steps
- Update `CLAUDE.md`, `docs/CLAUDE.md`: document Dokploy as deploy target
- **Phase 5.5 — Secrets rotation (BLOCKER fix):**
  - Rotate `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, all API keys
  - Securely delete old `/opt/skatelab/.env` with `shred -u`
  - Update Dokploy env with new secrets
- Delete `/opt/infra/` directory (or keep Caddy no-op as Phase 4 fallback)

**Pass criteria:**
- `grep -r "deploy.sh" .` returns no references
- `grep -r "compose.prod" .` returns no references
- CI green: builds + pushes images, no SSH deploy
- Dokploy auto-deploys on new `:latest` tag
- Old secrets no longer valid (rotation enforced)

## Risk Matrix

| Phase | Risk | Severity | Detection | Rollback time |
|-------|------|----------|-----------|---------------|
| 1 | Port conflict Dokploy vs Caddy | Low | `docker ps` shows port collision | < 5 min (down + restart) |
| 2 | Env vars missing in Dokploy | Medium | Health check fails, app 500s | < 1 min (Caddy switch) |
| 2 | Network not joined → DB unreachable | Medium | App crashloop, connection refused | < 1 min (Caddy switch) |
| 3 | Data loss in pg_dump/restore | High | Row count mismatch, FK errors | Hours (full restore from backup) |
| 3 | RustFS data not synced | High | Missing videos, broken thumbnails | Hours (re-sync from backup) |
| 4 | TLS cert not issued (Cloudflare plugin misconfig) | Medium | `curl https://` fails | < 5 min (revert Caddy) |
| 4 | Middleware missing → security regression | Medium | `curl -I` shows missing HSTS | < 5 min (revert Caddy) |
| 4 | SSE buffered → analysis hangs | High | Long-poll requests time out | < 5 min (revert Caddy) |
| 5 | Old file references in scripts | Low | `grep` finds references | Trivial (git revert) |

## Pre-Migration Checklist

- [ ] Snapshot `/opt/infra/` volumes: `tar -czf infra-volumes-$(date).tar.gz /var/lib/docker/volumes/`
- [ ] Snapshot `/opt/skatelab/` volumes: same
- [ ] Backup Postgres: `pg_dumpall > /opt/backups/migration-$(date)/postgres.sql`
- [ ] Backup Valkey: `BGSAVE` + copy RDB
- [ ] Backup ClickHouse: native backup or clickhouse-client dump
- [ ] Backup RustFS: `aws s3 sync s3://skatelab-pipeline s3://backup-bucket/migration-$(date)/`
- [ ] Test backup restore on separate machine (or stop prod, restore to empty container, validate)
- [ ] Verify Dokploy works on hello-world (Phase 1 done)
- [ ] Document current `docker rollout` behavior in `infra/.archive/`
- [ ] Notify team (if any) about cutover windows
- [ ] Keep old compose files in `/opt/{infra,skatelab}/.archive/` for 30 days

## Secrets Strategy

- Dokploy uses **env files** (UI upload per service or project-level). Format: copy current `.env` content as-is, paste into Dokploy service config.
- Per-service env files: `infra/.dokploy-envs/{service}.env` (created during migration, then uploaded to Dokploy UI)
- Old `/opt/skatelab/.env` kept as backup until Phase 5, then deleted
- GitHub Actions secrets (`JWT_SECRET_KEY`, `VASTAI_API_KEY`, `S3_*`, etc.) — unchanged (used only by build job, not deploy)
- Dokploy access: only via VPN (AmneziaWG subnet 10.99.0.0/24). External access to UI disabled via firewall rule.

## Monitoring

- Prometheus stays in Dokploy (Phase 2). Scrape targets updated:
  - `backend:8000/metrics` (new service name in Dokploy network)
  - `frontend:3000/metrics`
  - gpu-worker: stays on Vast.ai external, scrape URL unchanged
- Alert rules unchanged (`infra/prometheus/rules/alerts.yml`)
- PostHog alerts: PostHog moved to Dokploy, clickhouse target updates to new service name
- New alerts added:
  - `DokployDown` (UI/health check unreachable)
  - `TraefikCertExpiringSoon` (cert < 14 days to expiry)

## Cutover Pattern (zero-downtime)

For Phases 2, 3, 4:

1. New service deployed in Dokploy
2. Old service still running in compose
3. Caddyfile uses env var: `BACKEND_TARGET=old:8000` or `BACKEND_TARGET=host.docker.internal:8000`
4. Switch: `sed -i 's/old:8000/host.docker.internal:8000/' /opt/infra/caddy/Caddyfile && caddy reload`
5. Caddy reload picks up new target in < 1 sec
6. Monitor for 5 min, then proceed
7. Old service scaled down (or kept for 24h as fallback)

No DNS change → no propagation delay → no user-visible disruption.

## Open Questions

- **Dokploy version pinning:** pin to specific release (e.g., `dokploy/dokploy:v0.20.x`) for reproducibility. Update via Watchtower on Dokploy itself, not auto.
- **Traefik plugin Cloudflare DNS:** Dokploy ships with `traefik/traefik` + cloudflare plugin by default. Verify in Phase 1 hello-world test with real domain.
- **Prometheus storage retention:** current 30d (volume `prometheus-data` in compose). After migration: same volume, same retention, same alert rules. No change.
- **Dokploy backup strategy:** Phase 1 install. Phase 4 add: external cron to `/opt/backups/dokploy-$(date)/` for Dokploy config + project metadata (not volumes — those backed up separately).
- **Mobile app:** API base URL `api.skatelab.ru` unchanged. No mobile rebuild needed. Verified Phase 2 smoke test.
- **VPN-only access:** Dokploy UI on :18080, reachable only from AmneziaWG subnet 10.99.0.0/24. iptables rule added in Phase 1.

## Files to Modify

### Phase 1
- `infra/services/caddy/Caddyfile` (add VPN-only route to :18080)
- New: `infra/.dokploy-envs/{service}.env` (Dokploy env files, prepared for upload)

### Phase 2
- `infra/services/caddy/Caddyfile` (backend/frontend targets → Dokploy service names via shared network)
- `infra/prometheus/prometheus.yml` (compose service names → Dokploy service names)
- New: Dokploy project `skatelab` with 5 services
- `.github/workflows/deploy.yml` (document intent: strip SSH deploy in Phase 5)

### Phase 3
- `infra/services/caddy/Caddyfile` (per-batch target updates)
- `infra/prometheus/prometheus.yml` (additional service name updates)
- New: Dokploy project `infra` with DBs + services (5 batches)
- Postgres: add `pglogical` replication setup

### Phase 4
- `infra/services/caddy/Caddyfile` (drop routes handled by Traefik, keep no-op container as fallback)
- `infra/compose.yaml` (remove Caddy service after Phase 5)
- `infra/prometheus/prometheus.yml` (final service name updates)
- New: Traefik dynamic config with all 15+ routes + middlewares
- TLS cert import script (Caddy ACME → Traefik acme.json)

### Phase 5
- `.github/workflows/deploy.yml` (strip SSH deploy jobs, matrix builds, GHA cache)
- `CLAUDE.md`, `docs/CLAUDE.md` (document new deploy flow)
- Secrets rotation: `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, all API keys
- Delete: `infra/deploy.sh`, `infra/compose.prod.yaml` (after 30-day archive)
- Secure delete: `shred -u /opt/skatelab/.env`

## Success Criteria (overall)

- All 20+ services running in Dokploy
- All 15+ subdomains respond via Traefik
- Zero data loss (Postgres pglogical replication, RustFS background sync verified)
- Zero user-visible downtime during migration (Caddy no-op kept as Phase 4 fallback)
- GitHub Actions: CI + build only, no SSH (matrix builds, GHA cache, ~7-10 min critical path)
- 5 spec-breaking blockers fixed and validated in Phase 1 (network connectivity, worker queue isolation, Postgres replication, TLS cert handoff, network isolation automation)
- Rollback tested for each phase
- Old stack archived for 30 days, then deleted
- Secrets rotated in Phase 5.5, old .env securely deleted
