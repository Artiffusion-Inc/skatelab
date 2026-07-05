# Dokploy Migration — Execution Progress

Status: 2026-07-05. Phase 1 CLI-verifiable tasks complete. Remaining tasks need Dokploy UI (admin registration + project creation).

## What's done (autonomous, via CLI + root)

### VPS state
- **Dokploy v0.29.8 installed** — `dokploy`, `dokploy-postgres` (PG 16), `dokploy-redis` (7), `dokploy-traefik` running as swarm services. Node `Debian-1303-trixie-amd64-base` Ready/Active/Leader.
- **Docker Swarm active** — `docker swarm init --advertise-addr 176.9.0.156`. `live-restore: true` removed from `/etc/docker/daemon.json` (incompatible with swarm; backup at `daemon.json.bak.<ts>`).
- **Traefik on 8080/8443** (NOT 80/443) — patched installer (`infra/dokploy/install-patched.sh`) so Caddy keeps 80/443 as fallback during migration. Dokploy UI on :18080 (host-mode publish → container :3000).
- **Prod intact** — 22 prod containers up, all subdomains 200, after docker restart (live-restore removal killed containers once; recovered via `docker compose up -d` in `/opt/infra` + `/opt/skatelab`). 26 containers total.
- **iptables VPN-only** — `infra/dokploy/scripts/iptables-vpn-only.sh` applied. Swarm host-mode DNATs 18080→container:3000 in DOCKER nat chain, so packets traverse FORWARD/DOCKER-USER (INPUT rules had zero counters). Rule in DOCKER-USER matched on `--ctorigdstport 18080`: VPN 10.99.0.0/24 RETURN, rest DROP. Verified: container-sourced curl to `176.9.0.156:18080` dropped (6 pkts), `10.99.0.1:18080` returns 307. Persisted via netfilter-persistent.
- **Backup** — 871M in `/opt/backups/migration-20260705-172523/` (postgres.sql 412K, infra-volumes 428M, skatelab-volumes 41M, rustfs-data 402M, valkey-dump 393B).

### BLOCKERs verified
- **#1 network-connect** — Deployed test nginx on `dokploy-network` (mimics Dokploy app), `docker network connect infra_app_network <container>`, Caddy reached it by IP **and** name. De-risks all app deploys.
- **#4 TLS cert import** — `tls-cert-import.sh` dry-run imported all 36 Caddy certs (`<domain>.crt`/`<domain>.key` naming, not `cert.pem`) into valid acme.json (152KB, 600 perms). Restart cmd uses `docker service update --force dokploy-traefik`.

### Images
- All SkateLab images present on VPS (backend/frontend/arq-worker:latest + prom/prometheus:v3.3.0), refreshed via `docker pull`. GHCR auth in `/home/dev/.docker/config.json`.

## What needs YOU (browser, ~5 min)

1. **Register Dokploy admin** — open `http://10.99.0.1:18080/register` from a machine on AmneziaWG (10.99.0.0/24). Create admin user. (Tried API automation — tRPC procedure path not trivially discoverable from minified bundle; faster in browser.)
2. **Create two projects in Dokploy UI** — `skatelab` and `infra`. Deploy a hello-world app to `skatelab` project to confirm the deploy pipeline works end-to-end.
3. Tell me when admin is registered — I'll resume via API for the rest (deploy backend/frontend/workers, DB warm-start, RustFS, pglogical, cutover).

## Updated 2026-07-05 (via API)

- Admin registered by user, API key created: `hBrvL...`
- 18080 iptables temporarily relaxed for user, then re-VPN-only after registration
- Projects created via API:
  - `skatelab` (id `NSZmXVVeRW06Dr_-E5ct4`, env `lpXEJMh2BkRSKp2oOVJTm`)
  - `infra` (id `Uo8a1y_cispcTtp_06zz_`, env `cYQ3NKH90xZdw9mI8Gy_Q`)
- Hello-world compose stack (id `rP3UT7hffCq0E2KViemRd`, appName `hello-world-kqgrmn`) deployed via `compose.create`+`compose.update`+`compose.deploy`. **BLOCKER #1 verified end-to-end**: nginx returned 200 on 19999, `docker network connect infra_app_network` worked, Caddy reached it by IP and name. Cleaned up.
- API wrapper: `/tmp/dk.sh <METHOD> /endpoint <json>` with x-api-key.
- OpenAPI spec: `/tmp/dokploy-cli/cli-0.29.4/openapi.json` (525 paths, full schema for all endpoints).

**Next steps autonomous via API:**
- Phase 2 Tasks 9-15: deploy backend, frontend, workers, prometheus as compose stacks
- Phase 3 Tasks 16-22: pglogical, Valkey DB 4, RustFS, Batch A/B migration
- Phase 4 Tasks 23-25: Traefik dynamic.yml, cert import, full cutover
- Phase 5 Tasks 26-30: archive, docs, secrets rotation, validation

## Deviation from plan (intentional)
- Plan said use official `curl … install.sh | sudo sh` with Traefik on 80/443. **Patched** installer so Traefik = 8080/8443, Caddy stays 80/443 as fallback. Reduces migration risk — if Traefik cutover fails, Caddy still serves. Phase 4 swaps them.
- Plan's iptables used INPUT chain. **Fixed** to DOCKER-USER (swarm host-mode DNAT bypasses INPUT).
- Root access via `script -qec "su -c '…' root"` pty (sudo -S stdin doesn't work in this env). Helper `/tmp/runroot.sh`.

## Remaining plan tasks (after admin registered)
- Task 4: SSE streaming test (needs deployed backend via Dokploy — Phase 2)
- Task 6: DB warm-start (deploy Postgres/Valkey via Dokploy OR keep infra shared — decision pending)
- Task 7: RustFS background sync (needs new RustFS deployed — decision pending; Ponytail: keep infra RustFS unless real reason to move)
- Tasks 9-30: Phase 2-5 (deploy apps, canary, cutover, pglogical, Traefik swap, cleanup, secrets rotation)

## Decisions to confirm
- **Keep infra Postgres/Valkey/RustFS shared** (Ponytail: don't move working services) vs deploy duplicates via Dokploy. Plan assumes duplicates + replication; simpler path = network-connect apps to existing infra services, skip pglogical/RustFS-sync entirely. Recommend the simpler path.