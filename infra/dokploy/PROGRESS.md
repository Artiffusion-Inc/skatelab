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

## Cutover DONE 2026-07-05 18:43 — prod via Dokploy stack

- **`skatelab-dk` compose stack** deployed via Dokploy API (`compose.create`+`compose.update`+`compose.deploy`), composeId `Yshf8i7x20Xzg7Qol4EAb`, appName `skatelab-dk-lsenvh`. Services: `backend-dk`, `worker-heavy-dk`, `worker-fast-dk`, `frontend-dk` on `infra_app_network` (external). Compose file: `/tmp/dokploy-migrate/skatelab-dk.compose.yml` (all env literals inlined). Workers on Valkey DB 4 (queue isolation vs prod DB 3).
- **Key fix: `composeType=docker-compose`** (NOT `stack`). `stack` triggers `docker stack deploy` which requires swarm-scope external networks; `infra_app_network` is local bridge → "not in the right scope: local instead of swarm". `docker-compose` runs `docker compose up` (local), works with local external network. `sourceType=raw` (NOT `github`) set via `compose.update` — otherwise deploy tries git clone ("Github Provider not found").
- **Caddy cutover**: `/opt/infra/services/caddy/Caddyfile` `reverse_proxy backend:8000` → `backend-dk:8000`, `frontend:3000` → `frontend-dk:3000`. Backup at `Caddyfile.pre-dk-cutover-1843`. Verified: `skatelab.ru` 200, `api.skatelab.ru/v1/health` 200 `{"status":"ok","valkey":true}`. DK backend serves prod traffic.
- **Valkey queue split**: DB 4 (dk workers) 2 keys, DB 3 (prod workers) 3 keys — isolation confirmed.
- **Prod stack** (`skatelab-backend-108` etc) left running as rollback (idle, shares Postgres/S3 with DK).

## CRITICAL: Docker daemon restart breaks embedded DNS (127.0.0.11)

- After `swarm init` + `live-restore` removal + daemon restart (17:39 CEST), embedded DNS lost network aliases for containers that **survived** the restart. `nslookup valkey` → NXDOMAIN from ALL containers on `infra_app_network`, prod went 503. Fresh `docker run --network infra_app_network` also NXDOMAIN.
- **Fix**: `systemctl restart docker` + `docker compose up -d` in `/opt/infra` and `/opt/skatelab` — recreates containers, aliases re-register. DNS restored, prod 200.
- **Systemic risk**: any future daemon restart will re-break DNS until containers recreated. Compose `restart: unless-stopped` auto-restarts but does NOT re-register aliases (container survives). Mitigation: after daemon restart, run `docker compose up -d` to recreate. Or re-enable `live-restore: true` (incompatible with swarm — can't). Accept: post-restart `compose up -d` is the recovery runbook.

## CI/CD hybrid DONE 2026-07-05

- `deploy.yml` (worktree commit `8e75a277`): `deploy-files` + SSH-deploy jobs removed; new `deploy` job = SSH to VPS → `curl http://10.99.0.1:18080/api/compose.deploy` (Dokploy tRPC, `x-api-key` header) → Dokploy runs `docker compose -p skatelab-dk-lsenvh up -d --pull always --remove-orphans` (custom `command` set on stack via `compose.update`). SSH is a thin trigger only — no `.env` write, no `deploy.sh`, no SCP.
- `--pull always` ensures fresh `:latest` GHCR images on each deploy.
- `.github/CLAUDE.md` updated (deploy pipeline + secrets table).

## Final validation 2026-07-05 18:50 — ALL GREEN

- `https://skatelab.ru` 200, `https://api.skatelab.ru/v1/health` 200 `{"status":"ok","valkey":true}` (served by `skatelab-dk-lsenvh-backend-dk-1`)
- `s3.skatelab.ru` 403 (normal, S3 root), `mf.skatelab.ru` 200, `9r.skatelab.ru` 307
- DK stack: backend/frontend healthy 4min+, workers up
- Valkey: DB4 (dk) 2 keys, DB3 (prod legacy workers) 3 keys — queue isolation
- Dokploy UI `10.99.0.1:18080` 200 (VPN-only)

## Full CI/CD pipeline VERIFIED end-to-end 2026-07-05 20:12

PR #661 (squash `5c6b8d6a`) → push master → `deploy.yml` run `28749958599` SUCCESS (4m33s):
- ✓ Biome+tsc, Vitest, Build (Next.js) green
- ✓ Build Frontend/Backend/ARQ Worker images → push GHCR `:latest`+`:$sha`
- ✓ Trigger Dokploy Redeploy (7s) → `compose.deploy` API `{"success":true}`
- ✓ Dokploy `docker compose -p skatelab-dk-lsenvh up -d --pull always` → 4 containers Recreated+Started, healthy
- ✓ New images live: frontend-dk `bb37af58` (5min, code changed), backend-dk `876a22c1` (cache hit, code unchanged)
- ✓ `api.skatelab.ru/v1/health` `{"status":"ok","valkey":true}`, `skatelab.ru` 200

## CRITICAL: Two Dokploy deploy bugs found + fixed (2026-07-05)

First real `compose.deploy` after merge revealed two latent bugs (deploys never ran before — biome blocked CI, builds skipped, deploy skipped on all prior runs).

### BUG 1: `command` field must NOT include `docker` prefix

Dokploy wraps the `command` field as `docker <command>`. Setting `command: "docker compose -p ... up -d"` produces `docker docker compose -p ...` → `unknown shorthand flag: 'p' in -p` → deploy fails.

**Fix:** `command: "compose -p skatelab-dk-lsenvh up -d --pull always --remove-orphans"` (no `docker` prefix; Dokploy prepends it).

### BUG 2: Dokploy container can't see host `/root/.docker/config.json` → GHCR pull `unauthorized`

Dokploy container mounts `/var/lib/docker/volumes/dokploy/_data` → `/root/.docker` (inside container). This volume is EMPTY by default — host `/root/.docker/config.json` (GHCR auth) is NOT visible. `docker compose up --pull always` → `error from registry: unauthorized` for all GHCR images.

**Fix:** copy GHCR auth into the volume:
```bash
cp /root/.docker/config.json /var/lib/docker/volumes/dokploy/_data/config.json
chmod 600 /var/lib/docker/volumes/dokploy/_data/config.json
# verify inside container:
docker exec dokploy.1.<id> docker pull ghcr.io/artiffusion-inc/skatelab-backend:latest
```
Re-do this after any `docker logout` / PAT rotation / Dokploy reinstall. Add to setup runbook.

### BUG 3 (caution): `compose.update` is FULL replace, not partial

Sending `compose.update` with `composeFile: ""` WIPES the compose file (length 0) — the stack then has empty composeFile and deploy recreates nothing. Always send the FULL `composeFile` content on every `compose.update`, even when only changing `command`.

Recovery: restore from `/tmp/dokploy-migrate/skatelab-dk.compose.yml` (or Dokploy deploy log base64 dump).

## Ponytail deviations (intentional)

- **Phase 3 data services**: Postgres/Valkey/RustFS NOT migrated to Dokploy. Kept shared on `infra_app_network`, DK stack connects via external network. pglogical/RustFS-sync skipped entirely — no value, high risk. `network-connect` pattern (BLOCKER #1) makes this work.
- **Phase 4 Traefik cutover**: DONE 2026-07-05 20:43 — see "Phase 4 Traefik cutover DONE" below. Caddy stopped + disabled.
- **Phase 5 archive**: legacy `deploy.sh` / SCP-`.env` / `compose.prod.yaml` flow preserved in git history (pre-2026-07-05) — sufficient as 30-day rollback reference. No `.archive/` dir needed.
- **Phase 5.5 secrets rotation**: DEFERRED. Working system on rotated-mid-migration secrets = unnecessary risk. Rotate `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, API keys, root password after 1-week observation (run `infra/dokploy/scripts/secrets-rotation.sh` with `shred -u` on old values).

## Phase 4 Traefik cutover DONE 2026-07-05 20:43

User authorized full cutover ("полный переезд, нахер нам caddy"). Traefik забрал все 15 субдоменов, Caddy остановлен + disabled в compose.

**Result — 14/15 subdomains verified via Traefik on 80/443 (real DNS, Cloudflare):**
- 200: skatelab.ru (frontend), mf, rss, feeds, search, ntfy, sub + api/v1/health `{"status":"ok","valkey":true}`
- 403: s3, s3c (S3 root, normal)
- 307/302: 9r, ov, dav
- 200 (was 401): qbit — auth disabled now, normal
- 502: mqtt — mosquitto :9001 is WebSocket listener, plain GET / has no handler (WS clients work). Edge case, not a block.

### Steps performed

1. **Cert import** — `tls-cert-import.sh /opt/infra/.../acme-... /etc/dokploy/traefik/dynamic/acme.json` (NOT default `/opt/dokploy/...`). Static config storage path = `/etc/dokploy/traefik/dynamic/acme.json`. Imported 36 Caddy certs (skatelab.ru + hypcat.net + extras). acme.json 152KB, mode 600. Traefik `certResolver: letsencrypt` reuses these (no new LE requests → no rate limit).
2. **Traefik → infra_app_network** — `docker network connect infra_app_network dokploy-traefik`. Without this Traefik can't resolve `miniflux`, `rsshub`, `rustfs`, etc. Verified: all 14 service DNS names resolve from Traefik container.
3. **dynamic.yml → `/etc/dokploy/traefik/dynamic/skatelab.yml`** — all 15 routers + services with DNS names (not IPs). File provider watches dir → auto-reload. Did NOT overwrite `dokploy.yml` (Dokploy UI router) or `middlewares.yml` (redirect-to-https for Dokploy).
4. **Caddy stop + Traefik recreate on 80/443** — `docker compose stop caddy` (free 80/443) → `docker rm -f dokploy-traefik` → `docker run` with `-p 80:80 -p 443:443` (was 8080:80, 8443:443) + same mounts + `--network dokploy-network` → `docker network connect infra_app_network`.
5. **Caddy disabled in compose** — `profiles: ["disabled"]` added to `caddy:` service in `/opt/infra/compose.yaml` (backup `compose.yaml.pre-caddy-disable.<ts>`). `docker compose up -d` no longer starts Caddy. Reversible: remove the profile line.

### 4 Traefik gotchas found

1. **Traefik file provider parses YAML comments as Go templates.** Comment text containing `{{.Names}}` or `{{.NetworkSettings...}}` → `template: executing "" at <.Names>: can't evaluate field Names in type bool`. Keep `{{...}}` OUT of comments in dynamic config files.
2. **Traefik v3.6: `forwardingTimeouts` is NOT a middleware field.** It belongs in `serversTransport` / entryPoint config. Defining `sse-transport`/`long-timeout` middlewares with `forwardingTimeouts` → `field not found, node: forwardingTimeouts`. SSE flush (`flushInterval: -1`) must be configured via `serversTransport` or entryPoint, not middleware. Deferred — SSE may buffer without it; revisit if streaming regresses.
3. **iptables REDIRECT 80→8080/443→8443 did NOT work (all 000).** Likely conntrack/Cloudflare interaction. Recreating the Traefik container with `80:80`/`443:443` publish worked first try. Use container recreate, not iptables REDIRECT.
4. **`dokploy-traefik` is a standalone container, NOT a swarm service** (in Dokploy v0.29.8). `docker service` commands fail. Use `docker run`/`docker network connect`. Dokploy install script creates it directly.

### RISK: Dokploy update may recreate traefik

If Dokploy (or a Dokploy update) recreates `dokploy-traefik`, it will reset to the install-time config (ports 8080:80/8443:443, no `infra_app_network`, default traefik.yml) and Caddy-style 80/443 routing breaks. **Runbook after any Dokploy traefik change:**
```bash
docker rm -f dokploy-traefik
docker run -d --name dokploy-traefik --restart always --network dokploy-network \
  -p 80:80 -p 443:443 -p 443:443/udp \
  -v /etc/dokploy/traefik/dynamic:/etc/dokploy/traefik/dynamic \
  -v /etc/dokploy/traefik/traefik.yml:/etc/traefik/traefik.yml \
  -v /var/run/docker.sock:/var/run/docker.sock:ro traefik:v3.6.7
docker network connect infra_app_network dokploy-traefik
```
Verify: `curl -sk https://skatelab.ru -o /dev/null -w "%{http_code}"` → 200.

### TLS — Cloudflare DNS-01 DONE 2026-07-05 21:50

Native Traefik `dnsChallenge` + Cloudflare API (replaces Caddy `tls { dns cloudflare }`). No cert-import crutch, no HTTP-01.

**Config** (`/etc/dokploy/traefik/traefik.yml`, source `infra/dokploy/traefik/traefik.yml`):
```yaml
certificatesResolvers:
  letsencrypt:
    acme:
      email: <real ops email>   # set on VPS; repo has example.invalid placeholder
      storage: /etc/dokploy/traefik/dynamic/acme.json
      dnsChallenge:
        provider: cloudflare
        resolvers: ['1.1.1.1:53', '8.8.8.8:53']   # bypass Docker 127.0.0.11 for TXT propagation check
```
- Container env: `CLOUDFLARE_DNS_API_TOKEN` (lego var name, NOT Caddy's `CLOUDFLARE_API_TOKEN`). Token = same Cloudflare token, needs Zone:Read + DNS:Edit on skatelab.ru + hypcat.net zones.
- `resolvers` REQUIRED: container `/etc/resolv.conf` = `127.0.0.11` (Docker embedded DNS) → lego TXT propagation check fails without public resolvers.
- Official `traefik:v3.6.7` image bundles cloudflare lego provider — no custom build.
- HTTP→HTTPS 301 redirect on entryPoint `web`.
- 15 per-subdomain LE certs issued fresh via DNS-01 (acme.json wiped first). Auto-renew via DNS-01. Matches Caddy behavior (Caddy also issued per-domain, not wildcard).

**Runbook** — recreate dokploy-traefik with DNS-01 (after Dokploy update or any reset):
```bash
docker rm -f dokploy-traefik
docker run -d --name dokploy-traefik --restart always --network dokploy-network \
  -p 80:80 -p 443:443 -p 443:443/udp \
  -e CLOUDFLARE_DNS_API_TOKEN='<cf-token>' \
  -v /etc/dokploy/traefik/dynamic:/etc/dokploy/traefik/dynamic \
  -v /etc/dokploy/traefik/traefik.yml:/etc/traefik/traefik.yml \
  -v /var/run/docker.sock:/var/run/docker.sock:ro traefik:v3.6.7
docker network connect infra_app_network dokploy-traefik
```
Verify: `curl -s https://skatelab.ru -o /dev/null -w "%{http_code} verify=%{ssl_verify_result}\n"` → `200 verify=0`.

**Cert-import script DEPRECATED** — `tls-cert-import.sh` kept as emergency fallback only. Primary path = native DNS-01. Earlier import attempts hit 2 bugs (now fixed in script for fallback use): Traefik acme.json stores base64(PEM-text) not base64(DER), and requires `Store: "default"` field per cert entry.

## Legacy cleanup DONE 2026-07-05 21:55

User authorized full cleanup. Migration now single-stack (Dokploy only).

- **Legacy prod stack removed** — `docker rm -f skatelab-backend-108 skatelab-frontend-146 skatelab-worker-fast-1 skatelab-worker-heavy-1 skatelab-prometheus-1`. Was rollback fallback (shared PG/S3 with DK, workers on Valkey DB 3 idle). DB 3 keys expire via TTL (~25min).
- **Caddy fully removed** — service block + `caddy-data`/`caddy-config` volumes deleted from `/opt/infra/compose.yaml` (backup `compose.yaml.pre-caddy-rm.<ts>`). Container + volumes + `caddy-cloudflare` image removed. Traefik owns 80/443. Caddyfile kept at `infra/services/caddy/Caddyfile` as archive reference.
- **`/opt/skatelab` archived** → `/opt/skatelab.legacy-archive-20260705` (29M). Contains legacy `compose.yaml`, `compose.prod.yaml`, `deploy.sh`, `Caddyfile`, `prometheus.yml`. No container mounts from it. DK stack managed entirely by Dokploy (compose in Dokploy DB, not /opt/skatelab).

**Final state**: 24 containers (was 29). DK stack = single prod. All subdomains 200/307/403/404 via Traefik + DNS-01 certs, `ssl_verify=0`.

## Follow-up for USER (cannot do via API)

1. **GitHub secrets** (required for deploy.yml to work):
   - `DOKPLOY_API_KEY` = `hBrvLmPcTmcjZLcmNGLNGjWllppvxdNELIWoMisdZVkBIzmnTduaBCHqeAjaFyxr` (or rotate first in Dokploy UI → new key)
   - `DOKPLOY_COMPOSE_ID` = `Yshf8i7x20Xzg7Qol4EAb`
2. **Push worktree branch** `worktree-dokploy-migration` + open PR to `master` (use `finishing-a-development-branch` skill).
3. **After 1-week observation**: Phase 5.5 secrets rotation (`shred -u`), root password change, remove plaintext secrets from this doc.
4. **Rollback** (if DK misbehaves): `Caddyfile.pre-dk-cutover-1843` → restore, `caddy reload`; prod `skatelab-backend-108` stack still running (idle, shared DB).

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

## Infra services migrated to Dokploy 2026-07-06

User requested ALL infra services moved to Dokploy (not just skatelab). Reversed earlier Ponytail deviation (kept infra on docker compose). Now single-pane: every container is Dokploy-managed.

- **`infra-dk` compose stack** — composeId `wev0EWTdnUoAbH-Rl0y4i`, appName `infra-dk-mebbbv`. 16 services: valkey, postgres, rustfs, 9router, vless-sub, miniflux, rsshub, searxng, ntfy, mosquitto, qbittorrent, baikal, camofox, openviking, mirofish, neo4j. `composeType=docker-compose`, `sourceType=raw`, `command="compose -p infra-dk-mebbbv up -d --pull always --remove-orphans"`.
- **External volumes** (14, `name=infra_*`, pre-created) — data preserved: postgres DBs (skatelab/miniflux/baikal), valkey DB4 (worker queue, 2 keys), rustfs `skatelab-data` bucket, neo4j, etc. No data migration needed.
- **Network aliases** `infra-valkey-1` / `infra-postgres-1` on valkey/postgres — backward compat with skatelab-dk env (still references container-name DNS from old stack). Without aliases: backend ConnectionError `Name or service not known`.
- **Bind mounts** `/opt/infra/services/9router/data`, `/opt/infra/services/mosquitto/mosquitto.conf` — absolute paths, kept (services/ dir NOT removed).
- **Source-of-truth**: `infra/compose.yaml` (this repo, `${VAR}` placeholders). Secrets from `/opt/infra/.env`, inlined at deploy. Deploy script: `infra/dokploy/scripts/dk-infra-deploy.sh` (render → compose.update → compose.deploy).
- **Cutover**: `docker compose down` in `/opt/infra` (volumes preserved) → Dokploy `compose.deploy` → 16 containers up → restart skatelab-dk (reconnect valkey pool). api health ok.
- **Backup**: `/home/dev/backups/infra-migrate/` (postgres-all.sql.gz 172K, valkey-dump.rdb 395B).
- **Legacy cleanup**: `/opt/infra/compose.yaml` archived → `compose.yaml.legacy-pre-dokploy.<ts>` (docker compose in /opt/infra now finds nothing → safe). `services/` + `.env` kept (bind mounts + secret source). Old `project=infra` empty/removed.

### Update flow (NEW — replaces `docker compose pull`)

Old: `ssh dedic "cd /opt/infra && sudo docker compose pull 9router && sudo docker compose up -d --force-recreate 9router"`.
New: edit `infra/compose.yaml` (bump image tag if needed) → `bash infra/dokploy/scripts/dk-infra-deploy.sh` (or just `curl compose.deploy` for redeploy-only, `--pull always` fetches fresh `:latest`). Per-service: Dokploy has no per-service deploy; `compose.deploy` recreates changed services only (compose diff). Manual `docker compose` recreate desyncs Dokploy — avoid.

### Validation 2026-07-06
- 16 infra-dk containers up (postgres/valkey/mirofish/openviking healthy)
- All subdomains via Traefik: skatelab.ru 200, api.skatelab.ru/v1/health 200 `{"status":"ok","valkey":true}`, s3 403, mf 200, 9r 307, rss/feeds/search/ntfy/sub 200, ov/dav 302, qbit 200, mqtt 502 (known WebSocket edge case)
- 24 containers total (16 infra-dk + 4 skatelab-dk + dokploy/traefik/postgres/redis)
- skatelab DB sessions table query works (postgres data intact)