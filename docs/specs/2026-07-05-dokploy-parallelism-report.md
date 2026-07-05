# Dokploy Migration Parallelism Report

**Date:** 2026-07-05
**Status:** Draft — Synthesis of 5 specialist reviews
**Source spec:** `docs/specs/2026-07-05-dokploy-migration-design.md`

---

## TL;DR

- **Timeline compression:** The spec's 6-week sequential plan can drop to ~2.5–3 weeks by running Phase 2 service creation, Phase 3 DB provisioning, and Phase 3 utility-service batches in parallel. Background RustFS sync and DB warm-starting shift the Phase 3 data bottleneck into Phase 1.
- **Five spec-breaking blockers must be fixed before execution:** `host.docker.internal` fails on Linux Docker; worker queue dual-running causes job corruption; Postgres backup drift causes data loss; Let's Encrypt duplicate rate limits risk TLS failures; Dokploy network isolation requires explicit `docker network connect` automation.
- **CI/CD critical path cut:** Decoupling image builds from test results and adding GHA cache drops `deploy.yml` critical path from ~17–25 min to ~7–10 min, enabling multiple deploy-test-fix cycles per day during migration.
- **Only one true global big-bang:** Phase 4 Traefik port ownership (:80/:443). Everything else can be incremental or batched.
- **Overlap Phases 1 and 2:** As soon as Dokploy UI is reachable and hello-world deploys, begin creating `skatelab` project services. Waiting a full week is unnecessary.

---

## 1. Quick Wins (Can do today, low risk)

| # | Finding | Impact | Specialists |
|---|---------|--------|-------------|
| 1 | **Phase 2 parallel service creation:** Create backend, frontend, worker-heavy, worker-fast, and prometheus in Dokploy project `skatelab` simultaneously. They share the same image-source pattern and have no interdependencies. Saves ~2–3 days vs one-by-one. | Medium | Dependency Architect, Prior Art, Ops Async |
| 2 | **Phase 3 parallel DB provisioning:** Provision Postgres 17, Valkey, and ClickHouse in Dokploy project `infra` in parallel after the backup completes. Saves ~1–2 days. | Medium | Dependency Architect, Ops Async |
| 3 | **Phase 3 utility batch migration:** Migrate rsshub, searxng, ntfy, mosquitto, qbittorrent, and vless-sub as one parallel batch. They are network-only and have zero interdependencies. Saves ~3–4 days. | Medium | Dependency Architect, Ops Async |
| 4 | **Batch Caddyfile reloads:** Update Caddyfile targets per service group and run a single `caddy reload` per batch instead of per-service. | Low | Dependency Architect |
| 5 | **Phase 5 cleanup in parallel:** Archive files, update CI workflows, delete directories, and update docs can all run simultaneously. | Low | Dependency Architect |
| 6 | **CI: Matrix image builds:** Collapse `build-frontend`, `build-backend`, and `build-arq-worker` in `deploy.yml` into a single matrix job. Cuts ~140 lines to ~50 and makes adding new services trivial. | Low | CI/CD Parallel |
| 7 | **CI: Add GHA cache to image builds:** Add `cache-from type=gha` to `deploy.yml` image build steps (layer with existing registry cache). Reduces rebuild time on cache misses. | Low | CI/CD Parallel |
| 8 | **CI: Parallelize lint and typecheck:** Split `lint-typecheck` in `ci-reusable.yml` into two parallel jobs. `basedpyright` is the slowest step; running it separately shortens the Python critical path. | Low | CI/CD Parallel |
| 9 | **Ops: Automated health-check gate:** Replace manual "monitor 24h / wait 5 min" with a polling script (reuse `infra/deploy.sh` lines 54–58) that polls `/v1/health`, `/`, and worker queue depth after each Caddyfile switch. Exits 0 only when all checks pass within a configurable timeout (e.g., 2 min). Removes subjective wait times. | Low | Ops Async |
| 10 | **Ops: Image pre-pull in Phase 1:** Run `docker pull` for all GHCR images (`backend`, `frontend`, `arq-worker`, `prometheus`) in parallel on the VPS before creating Dokploy services. First deploys start instantly instead of pulling from GHCR. | Low | Ops Async |

---

## 2. Medium-Effort Parallelization (1–2 days work)

| # | Finding | Impact | Specialists |
|---|---------|--------|-------------|
| 11 | **CI: Remove CI from build critical path:** In `deploy.yml`, remove `needs:ci` from image build jobs. Image builds only need checkout + docker login; they do not depend on test results. Gate the final `deploy` job on both `ci` and `build-images` so production deploys stay safe, but images become available faster for smoke testing. Drops critical path from ~17–25 min to ~7–10 min. | High | CI/CD Parallel |
| 12 | **CI: Remove test gates from Docker jobs:** Remove `needs:test` from `docker-backend` and `needs:fe-check` from `fe-build` in `ci-reusable.yml`. Building a Containerfile does not require pytest to pass, and Next.js build catches type errors anyway. Adds parallelism without sacrificing correctness. | Medium | CI/CD Parallel |
| 13 | **CI: Fix cold Docker builds:** `docker-backend` and `docker-frontend` in `ci-reusable.yml` set up Blacksmith builder with `max-cache-size` but pass no `cache-from/cache-to` parameters. Every CI Docker build is cold. Add `type=gha` cache parameters. This is the single biggest CI cache win. | Medium | CI/CD Parallel |
| 14 | **CI: Skip redundant `uv sync`:** In `setup-python-venv` composite action, add a skip-if-restored guard: if `.venv/bin/python` exists and `pyproject.toml` mtime is older, skip `uv sync`. Saves 30–60s per Python job. | Low | CI/CD Parallel |
| 15 | **Ops: Background RustFS sync:** Start `aws s3 sync` from the old bucket to the new Dokploy-managed RustFS bucket during Phase 1 (as soon as new RustFS is provisioned). Run incremental sync nightly until Phase 3 cutover. This removes the serial data-copy dependency from Phase 3 and shrinks the RustFS cutover window to seconds. | High | Ops Async, Dependency Architect |
| 16 | **Ops: DB warm-start:** Provision Dokploy DB containers (Postgres 17, Valkey, ClickHouse) in Phase 1 immediately after hello-world. They can sit idle or be seeded with small datasets. During Phase 2/3, run `pg_dumpall` + restore, `BGSAVE` + RDB copy, and ClickHouse `BACKUP` + restore in parallel with SkateLab app validation. Overlaps Phase 2 and Phase 3 work. | High | Ops Async, Dependency Architect |
| 17 | **Ops: Parallel DB backups:** Run `pg_dumpall`, `valkey-cli BGSAVE`, and ClickHouse `BACKUP DATABASE` simultaneously (single script with background jobs) instead of sequentially. Total backup time drops to the duration of the slowest single backup. | Medium | Ops Async |
| 18 | **Ops: Canary subdomain routing:** Before cutting over `api.skatelab.ru` and `skatelab.ru` in Phase 2, add temporary Caddyfile blocks for `api-new.skatelab.ru` and `www-new.skatelab.ru` pointing to Dokploy-managed containers (via `docker network connect` resolution). Smoke-test login + video upload on canary URLs with real traffic. Once validated, switch the main domains in one reload. | Medium | Ops Async, Security Cutover |
| 19 | **Phase 3 batch chain migration:** Split remaining services into parallel batches: Batch A (RustFS, 9router — stateless/network layer), Batch B (miniflux, baikal — utility web services), Batch C (qbittorrent — file service), Batch D (neo4j + 9router in parallel, then openviking + mirofish after their dependencies are ready), Batch E (vless-sub). Each batch can be migrated and Caddyfile-updated independently. Reduces Phase 3 from ~2 weeks to ~3 days. | High | Ops Async, Dependency Architect |
| 20 | **Phase 4 config pre-writing:** Prepare all 15+ Traefik routes during Phase 3 while services are still on Caddy. Test routes against the Dokploy internal network before public cutover. Phase 4 becomes pure DNS cutover + monitoring, not config work. | Medium | Dependency Architect |
| 21 | **Phase 5 CI cleanup parallel with Phase 4:** Draft `.github/workflows/deploy.yml` changes (remove SSH deploy jobs) and documentation updates (`CLAUDE.md`, `docs/CLAUDE.md`) in a feature branch during Phase 2–4. Merge at Phase 5 start. These are repo-only changes with zero runtime impact. | Low | Ops Async |

---

## 3. Architectural Changes (Require spec revision)

| # | Finding | Impact | Specialists |
|---|---------|--------|-------------|
| 22 | **host.docker.internal does not work on Linux Docker** — The spec (line 136) proposes `host.docker.internal:8000` as the primary Caddy-to-Dokploy bridge. On standard Linux Docker this hostname does not resolve unless the daemon is reconfigured with `--add-host` or the userland proxy is enabled. Caddy reload will fail with "no such host" and the site will 502. This blocks the entire zero-downtime cutover pattern. **Decision:** Revise spec to use `docker network connect infra_app_network <dokploy-container>` as the primary pattern. Add a Phase 1 connectivity test that verifies Caddy can reach a Dokploy container by service name through the connected network. | High | Security Cutover, Dependency Architect |
| 23 | **Worker queue race condition during dual-running** — During Phase 2, old compose workers and new Dokploy workers both consume from Valkey DB 3. If the new worker image has code changes (schema expectations, arq version, task handler signatures), jobs enqueued by one version and picked up by the other can fail or corrupt data. Dual-running is unsafe for the worker tier. **Decision:** Add Valkey queue isolation to the spec. During Phase 2, new Dokploy workers use Valkey DB 4 (or a separate queue name prefix) while old workers drain DB 3. Switch the backend enqueue target atomically with the Caddyfile backend target change. | High | Security Cutover |
| 24 | **Postgres backup/restore is not atomic** — Old services continue writing to the source DB while `pg_dumpall` runs. The restored copy is stale on arrival; writes between dump start and switchover are lost. For a zero-downtime claim, this is data loss. **Decision:** Use Postgres logical replication (`pglogical`) to keep the new Dokploy Postgres in sync during Phase 3, then promote the replica at cutover. Alternative: enforce a brief read-only maintenance window on the old DB during the final dump. Document the chosen approach in the spec. | High | Security Cutover, Ops Async |
| 25 | **Let's Encrypt duplicate certificate rate limits** — Traefik will request new certificates for 15+ subdomains already held by Caddy. Let's Encrypt enforces a limit of 5 duplicate certificates per exact set of domains per week. Risk: domains without TLS and user-visible cert errors. **Decision:** Reuse existing Caddy ACME certificates by importing them into Traefik's store, or configure a single Cloudflare wildcard certificate instead of per-subdomain certs. Validate the chosen approach in Phase 1 with a non-production subdomain. | High | Security Cutover |
| 26 | **Dokploy network isolation** — Dokploy-managed containers run in isolated project networks by default. Cross-network DNS resolution from old compose services to new Dokploy DBs (and vice versa) fails unless explicitly connected to `infra_app_network`. The spec assumes services "join this network" but Dokploy does not automate this. **Decision:** Add explicit automation to the spec: use Docker network labels or a Dokploy post-create hook to run `docker network connect infra_app_network <container>`. Test network connectivity in Phase 1 before any data migration. This is a single-point-of-failure manual step. | High | Dependency Architect, Ops Async |
| 27 | **Secrets rotation plan missing** — Secrets in `/opt/skatelab/.env` persist on disk until Phase 5 (week 6) with no secure deletion (`shred`) and no rotation of `JWT_SECRET_KEY` or `POSTGRES_PASSWORD` after migration. A compromised backup or leftover file grants indefinite access. **Decision:** Add a Phase 5.5 secret rotation step to the spec: rotate `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and any API keys; securely delete the old `.env` with `shred -u`. | Medium | Security Cutover |
| 28 | **MiroFish local image unsupported** — MiroFish uses `pull_policy: never` with `localhost/mirofish-local:latest`. Dokploy may not support local images without a registry. **Decision:** Pre-migration, push the MiroFish image to GHCR (or another registry) and update the Dokploy service config to pull from there. Alternatively, configure Dokploy to build from a Dockerfile in the repo. Verify image availability in Phase 1. | Medium | Dependency Architect |
| 29 | **ClickHouse service missing from compose.yaml** — The spec mentions ClickHouse backup/restore and lists ClickHouse in the "After" architecture diagram, but the service is missing from `infra/compose.yaml`. **Decision:** Verify whether ClickHouse is actually deployed, planned, or referenced by PostHog/Plausible. If it does not exist, remove it from the migration scope. If it does exist, locate its compose file and include it in backups. | Medium | Dependency Architect |
| 30 | **Prometheus scrape target breakage** — Prometheus scrape targets reference compose service names (`backend:8000`, `frontend:3000`). When services move to Dokploy, service discovery breaks unless `prometheus.yml` is updated. This couples Phase 2/3 to prometheus config changes. **Decision:** Add explicit `prometheus.yml` updates to the spec's Phase 2 and Phase 4 file-modification lists. Include a validation step that confirms scrape targets return 200 before old containers are stopped. | Medium | Dependency Architect |
| 31 | **SSE / streaming buffering parity** — Caddy `flush_interval -1` must map exactly to Traefik transport `flushInterval: -1`. If Dokploy's Traefik UI does not expose this setting, raw Traefik dynamic config labels or a file provider are required. **Decision:** Add a Phase 1 validation test that streams an SSE endpoint through Dokploy's Traefik and verifies no buffering. If the setting is not exposed, document the raw label workaround in the spec before Phase 4. | Medium | Prior Art, Ops Async |
| 32 | **Traefik wildcard DNS challenge requirement** — Traefik wildcard certificates require a Cloudflare DNS challenge, not an HTTP challenge. Dokploy discussion #3089 confirms wildcard rules only work with wildcard certs via DNS challenge or own certs. **Decision:** Validate Cloudflare DNS challenge configuration in Phase 1 with a test subdomain. Do not assume HTTP challenge will work for wildcards. | Medium | Prior Art |
| 33 | **Dokploy compose-service downtime** — Dokploy issue #2497 confirms native Docker Compose deployment stops the old container before starting the new one, causing 5–10s downtime. The spec's Caddy-facade pattern correctly routes around this for Phases 2–3, but Phase 4 (Traefik owns all routing) reintroduces the risk. **Decision:** For Phase 4, rely on Traefik health checks + Dokploy rolling restart if available. Keep a Caddy no-op container as an emergency fallback until Dokploy zero-downtime compose support lands. Document the fallback in the spec. | Medium | Ops Async, Prior Art |

---

## 4. Conflicts and Decisions

### Conflict 1: host.docker.internal vs docker network connect
- **Spec says:** Use `host.docker.internal:8000` as the primary Caddy-to-Dokploy bridge (line 136).
- **Specialists say:** Security Cutover proves this hostname does not resolve on standard Linux Docker. Caddy will 502. Dependency Architect identifies `docker network connect infra_app_network <dokploy-container>` as the working alternative.
- **Decision:** Revise the spec to make `docker network connect` the **primary** pattern. Add a Phase 1 test that confirms Caddy can reach a Dokploy-managed container by service name through the connected network. Only fall back to host networking if network connect fails.

### Conflict 2: CI as gate vs CI off the critical path
- **Spec implies:** CI passes before deploy.
- **Specialists say:** CI/CD Parallel recommends removing `needs:ci` from image build jobs so images are built and pushed faster. This is safe if branch protection enforces CI on PRs, but risky if direct pushes to master bypass CI.
- **Decision:** Remove `needs:ci` from image build jobs, but keep the final `deploy` job gated on both `ci` and `build-images`. Images become available sooner for Dokploy smoke tests; production deploys remain protected. Add a note to the spec that branch protection rules must enforce CI on PRs.

### Conflict 3: Worker dual-running assumed safe
- **Spec assumes:** Phase 2 dual-running (old + new workers) is safe because Caddy routes traffic.
- **Specialists say:** Security Cutover identifies a concrete race condition: old and new workers consume the same Valkey queue (DB 3). Version-mismatched jobs can fail or corrupt data. Caddy only routes HTTP traffic, not queue workers.
- **Decision:** Add **Valkey queue splitting** to the spec. During Phase 2, new Dokploy workers consume from Valkey DB 4 (or a prefixed queue name). The backend enqueue target is switched atomically with the Caddyfile backend target change. Old workers drain DB 3 before being scaled down.

### Conflict 4: Phase 1 duration
- **Spec allocates:** A full week for Phase 1.
- **Specialists say:** Ops Async argues that Phase 2 service creation can begin as soon as hello-world passes. Waiting a full week is unnecessary and delays the critical path.
- **Decision:** **Overlap Phase 1 and Phase 2.** As soon as Dokploy UI is reachable via VPN and a hello-world app deploys successfully, begin creating `skatelab` project services in parallel with Phase 1 documentation and final verification. These services are not publicly routed until Caddyfile updates in Phase 2, so there is zero user-facing risk.

---

## 5. Specialist Attribution Table

| Finding Area | Dependency Architect | Prior Art Researcher | CI/CD Parallel | Security Cutover | Ops Async |
|--------------|----------------------|----------------------|----------------|------------------|-----------|
| Parallel Phase 2 service creation | X | X | | | X |
| Parallel Phase 3 DB provisioning | X | X | | | X |
| Parallel Phase 3 utility batch | X | X | | | X |
| Phase 3 chain services (neo4j/9router -> OV/MF) | X | | | | |
| RustFS as Phase 3 critical path | X | | | | X |
| host.docker.internal Linux failure | | | | X | X |
| Worker queue race condition | | | | X | |
| Postgres backup drift / data loss | | | | X | X |
| Let's Encrypt rate limits | | | | X | |
| Network isolation / docker connect | X | | | | X |
| CI build matrix / GHA cache | | | X | | |
| Remove CI from build critical path | | | X | | |
| Remove test gates from Docker jobs | | | X | | |
| Skip redundant uv sync | | | X | | |
| RustFS background sync | X | X | | | X |
| DB warm-start / Phase 1-2 overlap | | | | | X |
| Health-check polling gate | | | | | X |
| Canary subdomain routing | | | | X | X |
| Traefik SSE flush parity | | X | | | X |
| Dokploy compose downtime (#2497) | | X | | | X |
| Cloudflare wildcard DNS challenge | | X | | | |
| MiroFish local image | X | | | | |
| ClickHouse missing from compose | X | | | | |
| Secrets rotation missing | | | | X | |
| Prometheus scrape target coupling | X | | | | |
| No one-click import / manual recreation | | X | | | |
| Traefik load-balancer port auto-detection | | X | | | |
| Dokploy auto-deploy polling limitation | | X | | | |

---

*End of report.*
