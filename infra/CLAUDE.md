# infra/CLAUDE.md

## Server

Dedic: 176.9.0.156, 8 CPU / 62GB RAM / 905GB disk (Hetzner)

| User | Groups | sudo | Home | Purpose |
|------|--------|------|------|---------|
| admin | admin | ALL NOPASSWD | /home/admin | System admin. Deploys, Docker management. |
| dev | dev, docker | none | /home/dev | Development. Runs local dev services. |

Root SSH disabled. `admin` — единственный с sudo. Port 43210, key-only.

- `ssh dedic` → admin (sudo)
- `ssh dedic-dev` → dev (no sudo)

## How to Tell Which Machine

| Check | Local (Artix) | Dedic (Debian) |
|-------|----------------|----------------|
| `hostname` | `m7600qe` | `dedic` |
| `ip addr show awg0` | `10.99.0.2/24` | `10.99.0.1/24` |
| Prompt | `~ ❯` (zsh, user) | `admin@dedic:~$` or `dev@dedic:~$` |
| Init system | dinit | systemd |
| Package manager | pacman | apt |
| Container runtime | podman (local) | docker (dedic) |

SSH connections: `ssh dedic` (admin) / `ssh dedic-dev` (dev). If shell shows `dedic` in prompt → remote.

- **All infra managed from repo**: edit files in `./infra/`, then `scp` to dedic
- **Deploy flow**: edit → `scp <file> dedic:/tmp/<file>` → `ssh dedic "sudo mv /tmp/<file> /opt/infra/..."` → reload if needed
- **Caddyfile**: always `caddy fmt` before deploy
- **Secrets**: never hardcode in compose — use env vars from `/opt/infra/.env`

## Three Areas

| Area | Path | Content | Deploy |
|------|------|---------|--------|
| **infra** | `/opt/infra/` | Shared services: PG, Valkey, RustFS, Caddy, utility | Manual `docker compose up -d` |
| **prod** | `/opt/skatelab/` | SkateLab app: backend, frontend, prometheus | CI/CD via GitHub Actions |
| **dev** | `/home/dev/skatelab/` | Code and files, no Docker containers | Manual development |

## Docker Networks

- `infra_app_network` — shared by infra + skatelab stacks
- `dev_default` — dev postgres + valkey (isolated from infra)

## Shared Infrastructure

### Valkey (Redis-compatible)

| DB Index | Consumer | Purpose |
|----------|----------|---------|
| 0 | — | Default (unused) |
| 2 | — | Available (was PostHog self-hosted) |
| 3 | SkateLab | Task queue (arq) |

Service resolves as `infra-valkey-1` on `infra_app_network`.

### PostgreSQL

| Service | PG Version | DB | User | Purpose |
|---------|------------|----|------|---------|
| `postgres` | 17 | `skatelab`, `miniflux`, `baikal` | `skatelab` | SkateLab + utility DBs |

On `infra_app_network`. Auto-created by `init-dbs.sh` (SkateLab PG only).

### RustFS (S3-compatible)

| Endpoint | Access | Purpose |
|----------|--------|---------|
| `infra-rustfs-1:9000` | S3 API | SkateLab videos |
| `infra-rustfs-1:9001` | Console | Admin UI |

Caddy: `s3.skatelab.ru` → :9000, `s3c.skatelab.ru` → :9001.

**RustFS alpha risk:** Alpha software (1.0.0-alpha.89), may crash under high concurrency (512+ threads). `S3_*` abstraction allows switching backends by changing endpoint.

### AmneziaWG VPN (point-to-point)

AmneziaWG = obfuscated WireGuard. Resists DPI blocking (Russia blocks WireGuard protocol).

| Peer | IP | Role |
|------|----|------|
| dedic (server) | 10.99.0.1 | Gateway to all services |
| local (client) | 10.99.0.2 | Dev workstation |

- Config: `infra/services/amneziawg/` (`dedic.conf`, `local.conf`)
- AWG obfuscation params: Jc=4, Jmin=64, Jmax=256, S1-S4, H1-H4 (must match on all peers)
- Split tunnel: `AllowedIPs = 10.99.0.0/24` only — no full tunnel
- Dev access: services on `0.0.0.0` reachable at `10.99.0.1:<port>`, `127.0.0.1`-bound services need socat or `--host 0.0.0.0`
- iptables: INPUT policy DROP, `10.99.0.0/24` ACCEPT — services visible only via VPN

## PostHog Analytics

**PostHog Cloud (US region)** — `https://us.i.posthog.com`. No self-hosted services.

Self-hosted config preserved in `/opt/posthog/compose.yaml` for potential future migration.

| Var | Value |
|-----|-------|
| `POSTHOG_API_KEY` | Server-side key |
| `POSTHOG_HOST` | `https://us.i.posthog.com` |
| `NEXT_PUBLIC_POSTHOG_KEY` | `phc_sLhZ2BmHhJNb9f2TP56gnNkUcYxgVn7j6jN3orhXDWZk` |
| `NEXT_PUBLIC_POSTHOG_HOST` | `https://us.i.posthog.com` |

## Commands

| Action | Command |
|--------|--------|
| Start infra | `cd /opt/infra && docker compose up -d` |
| Caddy reload | `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` |
| Caddy fmt | `caddy fmt --overwrite /etc/caddy/Caddyfile` |
| Backup all DBs | `sudo /usr/local/bin/backup-dbs.sh` |
| Valkey DBs info | `docker compose exec valkey valkey-cli INFO keyspace` |
| SkateLab PG shell | `docker compose exec postgres psql -U skatelab` |
| AWG up (dedic) | `sudo awg-quick up awg0` |
| AWG down (dedic) | `sudo awg-quick down awg0` |
| AWG status | `sudo awg show awg0` |
| AWG up (local) | `dinitctl start awg` |
| AWG down (local) | `dinitctl stop awg` |
| iptables save | `sudo iptables-save > /etc/iptables/rules.v4` |

## Docker Stacks

### SkateLab Prod — `/opt/skatelab/compose.yaml`

Backend + Frontend + Prometheus on `infra_app_network`. Uses infra Postgres (`skatelab` DB) + infra Valkey (DB 3).

### Infra — `/opt/infra/compose.yaml`

Caddy reverse proxy (owns :80/:443) + self-hosted services. All subdomains on `skatelab.ru`.

**SkateLab-critical:**

| Service | Subdomain | Notes |
|---------|-----------|-------|
| Postgres (PG 17) | — | Shared DB: `skatelab`, `miniflux`, `baikal` |
| Valkey | — | Shared cache/queue. DB 3 (SkateLab) |
| RustFS | s3/s3c.skatelab.ru | S3 storage |
| Caddy | *.skatelab.ru | TLS via Cloudflare DNS challenge |
| AmneziaWG | — | Point-to-point VPN (host network, port 51820/udp) |
| vless-sub | 9r.skatelab.ru | Proxy subscription aggregator |

**SkateLab supporting:** AmneziaWG (dev VPN), Mosquitto (MQTT)
**Personal/utility:** Miniflux, RSSHub, SearXNG, cAdvisor, ntfy, Syncthing, qBittorrent, Baikal, OpenViking, MiroFish+Neo4j, Tor
**PostHog:** Migrated to Cloud. Self-hosted removed from compose.

### Dev — `/home/dev/skatelab/`

No containers. Dev runs backend locally, connects to infra services via network.

## Gotchas

- Docker DNS: shared infra resolves as `infra-valkey-1`/`infra-rustfs-1` (compose project prefix), NOT `valkey`/`rustfs`
- Valkey DB indices: 0 unused, 2=available, 3=SkateLab — never overlap
- S3_PATH_STYLE=true required for self-hosted S3 (RustFS). Without `s3={"addressing_style": "path"}` boto3 generates virtual-hosted URLs
- S3_REGION must be `us-east-1` (not `auto` which is R2-specific) — RustFS doesn't recognize `auto`
- AWG iptables: `10.99.0.0/24` ACCEPT in INPUT chain — required for VPN access. If iptables flushed, re-add
- AWG dev access: services must bind `0.0.0.0` (not `127.0.0.1`) to be reachable via 10.99.0.1
- AWG split tunnel: only `10.99.0.0/24` routed through VPN — no full tunnel
- vless-sub: env vars `HWID`, `VLESS_SUB_URLS` required in `/opt/infra/.env`
- vless-sub image: `docker.io/xpos587/vless-sub-server:latest` — custom, not on Docker Hub

## Deploy

GitHub Actions → `master` → CI → GHCR images → SCP deploy files + .env → `ssh admin@dedic /opt/skatelab/deploy.sh`

Sequence: pull images → `docker rollout` backend/frontend (zero-downtime) → copy Caddyfile → `caddy reload` → `alembic upgrade head` → health check (2min) → image prune. Rollback on alembic failure.

## Backups

Daily 04:00 via cron (`/usr/local/bin/backup-dbs.sh`), 7-day retention:

- PG 17: `pg_dumpall` → `/opt/infra/backups/postgres/`
- Neo4j: `neo4j-admin dump` (60s downtime) → `/opt/infra/backups/neo4j/`
- Config: tar (env, Caddyfile, iptables, sshd) → `/opt/infra/backups/config/`

## Environment Variables

See `backend/app/config.py` for full list. Infra-specific vars in `/opt/infra/.env`:

- Infra: `POSTGRES_PASSWORD`, `HWID`, `VLESS_SUB_URLS`, `CLOUDFLARE_API_TOKEN`
- SkateLab: `DATABASE_URL`, `VALKEY_URL`, `S3_*`, `VASTAI_API_KEY`, `JWT_SECRET_KEY`, `RESEND_API_KEY`
- PostHog (Cloud): `POSTHOG_API_KEY`, `POSTHOG_HOST`, `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST`, `POSTHOG_PERSONAL_API_KEY`