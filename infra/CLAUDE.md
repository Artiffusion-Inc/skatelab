# infra/CLAUDE.md

## Server

Dedic: 176.9.0.156, 8 CPU / 62GB RAM / 905GB disk (Hetzner)

### Users

| User | Groups | sudo | Home | Purpose |
|------|--------|------|------|---------|
| admin | admin | ALL NOPASSWD | /home/admin | System admin. Deploys, Docker management. |
| dev | dev, docker | none | /home/dev | Development. Runs local dev services. |

Root SSH disabled. `admin` — единственный с sudo.

### SSH

Port 43210, key-only, no passwords.

- `ssh dedic` → admin (sudo)
- `ssh dedic-dev` → dev (no sudo)

## Docker Networks

- `infra_app_network` — shared by infra + skatelab stacks
- `dev_default` — dev postgres + valkey (isolated from infra)

## Docker Stacks

### SkateLab Prod — `/opt/skatelab/compose.yaml`

Backend + Frontend + Prometheus on `infra_app_network`.

- Backend: `ghcr.io/artiffusion-inc/skatelab-backend:latest` (2GB mem limit)
- Frontend: `ghcr.io/artiffusion-inc/skatelab-frontend:latest` (512MB)
- Prometheus: `127.0.0.1:9090` (not proxied via Caddy)

Uses infra Postgres (`skatelab` DB) + infra Valkey (DB index 3).

### Infra — `/opt/infra/compose.yaml`

Caddy reverse proxy (owns :80/:443) + self-hosted services. All subdomains on `skatelab.ru`.

**SkateLab-critical:**

| Service | Subdomain | Notes |
|---------|-----------|-------|
| Postgres | — | Shared DB: `skatelab`, `miniflux`, `windmill`, `baikal` (auto-created by `init-dbs.sh`) |
| Valkey | — | Shared cache/queue. SkateLab uses DB index 3 |
| Caddy | *.skatelab.ru | TLS via Cloudflare DNS challenge. Proxies all subdomains |

**SkateLab supporting:**

| Service | Subdomain | Notes |
|---------|-----------|-------|
| Headscale | headscale.skatelab.ru | Tailscale-compatible VPN |
| Mosquitto | mqtt.skatelab.ru | MQTT broker (IMU data pipeline) |
| Android Emulator | — | Containerized, 127.0.0.1:5555 (CI testing) |

**Personal / utility:**

| Service | Subdomain | Notes |
|---------|-----------|-------|
| Miniflux | rss.skatelab.ru | RSS reader |
| RSSHub | feeds.skatelab.ru | RSS aggregator |
| Windmill | wm.skatelab.ru | Workflow automation |
| SearXNG | search.skatelab.ru | Meta-search engine |
| cAdvisor | monitor.skatelab.ru | Container metrics (basic auth) |
| ntfy | ntfy.skatelab.ru | Push notifications |
| Syncthing | sync.skatelab.ru | File sync |
| qBittorrent | qbit.skatelab.ru | Torrent client |
| Baikal | dav.skatelab.ru | CalDAV/CardDAV |
| 9Router | 9r.skatelab.ru | 9P router |
| OpenViking | ov.skatelab.ru | Console :8020, proxy :1933 |
| MiroFish | mf.skatelab.ru | AI app (uses Neo4j) |
| Neo4j | — | Graph DB for MiroFish |
| Tor | — | SOCKS proxy :9150 |

### Dev — `/home/dev/skatelab/`

dev-postgres (127.0.0.1:5432, db: `skatelab`, user: `skatelab`, pass: `skatelab_dev`) + dev-valkey (127.0.0.1:6379). No git repo — just `.next` build cache.

## Deploy

GitHub Actions pushes to `master` → CI → build GHCR images → SCP deploy files + .env → `ssh admin@dedic /opt/skatelab/deploy.sh`

Deploy sequence: pull images → `docker rollout` backend/frontend (zero-downtime) → copy Caddyfile → `caddy reload` → `alembic upgrade head` → health check (2min timeout) → image prune. Rollback on alembic failure.

## Backups

Daily 04:00 via cron (`/usr/local/bin/backup-dbs.sh`):

- Postgres: `pg_dumpall` (hot, no downtime) → `/opt/infra/backups/postgres/`
- Neo4j: `neo4j-admin dump` (60s downtime) → `/opt/infra/backups/neo4j/`
- Config: tar (env, Caddyfile, iptables, sshd) → `/opt/infra/backups/config/`
- Retention: 7 days

## Local Development

`infra/compose.yaml` starts Valkey (6379) + Postgres (5432, db: `src`, user: `skatelab`) via podman compose.

## Container Build

`infra/Containerfile`: multi-stage Python 3.11 + uv + bun. Copies `backend/`, `ml/`, `data/`, builds frontend. Excludes `docs/`, `experiments/`, `infra/`.

## GPU Worker

`ml/gpu_server/Containerfile` — 4.9GB, no torch/timm/triton. `ghcr.io/Artiffusion-Inc/skatelab-worker:latest`

## Environment Variables

See `backend/app/config.py`. Key: `DATABASE_URL`, `VALKEY_URL`, `R2_*`, `VASTAI_API_KEY`, `JWT_SECRET`, `RESEND_API_KEY`