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

SSH connections: `ssh dedic` (admin) / `ssh dedic-dev` → zellij auto-start. If shell shows `dedic` in prompt → remote.

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

### PostgreSQL

| Service | PG Version | DB | User | Purpose |
|---------|------------|----|------|---------|
| `postgres` | 17 | `skatelab`, `miniflux`, `baikal` | `skatelab` | SkateLab + utility DBs |

### RustFS (S3-compatible)

| Endpoint | Access | Purpose |
|----------|--------|---------|
| `rustfs:9000` | S3 API | SkateLab videos |
| `rustfs:9001` | Console | Admin UI |

Caddy: `s3.skatelab.ru` → :9000, `s3c.skatelab.ru` → :9001. S3 API returns 501 on `/` (normal — no root handler).

Credentials: `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` from `.env` (not `S3_ACCESS_KEY`).

### AmneziaWG VPN (point-to-point)

AmneziaWG = obfuscated WireGuard. Resists DPI blocking (Russia blocks WireGuard protocol).

| Peer | IP | Role |
|------|----|------|
| dedic (server) | 10.99.0.1 | Gateway to all services |
| local (client) | 10.99.0.2 | Dev workstation |
| phone (Android) | 10.99.0.3 | Mobile access via WG Tunnel app |

- Config: `infra/services/amneziawg/` (`dedic.conf`, `local.conf`)
- AWG obfuscation params: Jc=4, Jmin=64, Jmax=256, S1-S4, H1-H4 (must match on all peers)
- Split tunnel: `AllowedIPs = 10.99.0.0/24` only — no full tunnel
- Dev access: services on `0.0.0.0` reachable at `10.99.0.1:<port>`, `127.0.0.1`-bound services need socat or `--host 0.0.0.0`
- iptables: INPUT policy DROP, `10.99.0.0/24` ACCEPT — services visible only via VPN

### 9router (AI gateway)

Port 20128. Routes LLM + embedding requests to providers (combo routing).

| Model | Provider | Notes |
|-------|----------|-------|
| `groq/llama-3.3-70b-versatile` | Groq | JSON-capable, fast — used by MiroFish |
| `deepseek-v4-pro` | combo | Reasoning model, streams `reasoning_content` |
| `jina/jina-embeddings-v3` | Jina | Embeddings via `/v1/embeddings` — used by OV + MF |

Internal Docker URL: `http://9router:20128/v1` (no SSL, no external DNS). Use this inside containers, not `https://9r.hypcat.net/v1`.

### OpenViking

Subdomain: `ov.skatelab.ru`. Port 1933 (API) + 8020 (console).

Config via `OPENVIKING_CONF_CONTENT` env var:
- `server.root_api_key`: from `OPENVIKING_API_KEY` in `.env`
- `embedding.dense.provider`: `jina` via 9router (`jina/jina-embeddings-v3`)
- `vlm.provider`: `openai` via 9router (`deepseek-v4-pro`)

### MiroFish + Neo4j

Subdomain: `mf.skatelab.ru`. Local image `localhost/mirofish-local:latest` (`pull_policy: never`).

Caddy routes:
- `/api/*` + `/health` → `mirofish:5001` (Flask backend)
- everything else → `mirofish:3000` (Vite dev server)

| Config | Value | Notes |
|--------|-------|-------|
| `ZEP_BACKEND` | `graphiti` | Local Neo4j (not Zep Cloud) |
| `LLM_BASE_URL` | `http://9router:20128/v1` | Internal Docker network |
| `LLM_MODEL_NAME` | `groq/llama-3.3-70b-versatile` | 9router combo, JSON-capable |
| `GRAPHITI_EMBEDDING_MODEL` | `jina/jina-embeddings-v3` | 9router Jina embeddings |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j 5 container |

MiroFish dev server: `--host 0.0.0.0 --port 3000 --config vite.host.mjs` (allowedHosts for `mf.skatelab.ru`).

### Mosquitto (MQTT)

Subdomain: `mqtt.skatelab.ru`. Caddy proxies WebSocket to `mosquitto:9001`. TCP port 1883 on localhost only.

## PostHog Analytics

**PostHog Cloud (US region)** — `https://us.i.posthog.com`. No self-hosted services.

## Commands

| Action | Command |
|--------|--------|
| Start infra | `cd /opt/infra && docker compose up -d` |
| Pull images | `cd /opt/infra && docker compose pull` |
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
| Caddy | *.skatelab.ru | TLS via Cloudflare DNS challenge (`caddy-cloudflare` image) |
| 9router | 9r.skatelab.ru | AI gateway (LLM + embeddings) |
| AmneziaWG | — | Point-to-point VPN (host network, port 51820/udp) |
| vless-sub | sub.skatelab.ru | Proxy subscription aggregator |

**Personal/utility:** Miniflux, RSSHub, SearXNG, ntfy, Mosquitto, qBittorrent, Baikal, OpenViking, MiroFish+Neo4j

**Removed:** cAdvisor, Tor

### Dev — `/home/dev/skatelab/`

No containers. Dev runs backend locally, connects to infra services via network.

## Gotchas

- Docker DNS: services resolve by service name (`valkey`, `rustfs`, `9router`) on same network, NOT by container name
- Valkey DB indices: 0 unused, 2=available, 3=SkateLab — never overlap
- S3_PATH_STYLE=true required for self-hosted S3 (RustFS). Without `s3={"addressing_style": "path"}` boto3 generates virtual-hosted URLs
- S3_REGION must be `us-east-1` (not `auto` which is R2-specific) — RustFS doesn't recognize `auto`
- RustFS credentials: `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY` in `.env`, NOT `S3_ACCESS_KEY`
- 9router inside Docker: use `http://9router:20128/v1` (not `https://9r.hypcat.net/v1` — SSL cert mismatch)
- 9router models with `ollama/` prefix require local ollama server — use bare model names for combo routing
- MiroFish: `pull_policy: never` for local image — `docker compose pull` skips it
- MiroFish: Vite needs `--host 0.0.0.0` + `allowedHosts` for Caddy proxy
- MiroFish: `ZEP_BACKEND=graphiti` (not `cloud`) — uses Neo4j, not Zep Cloud
- AWG iptables: `10.99.0.0/24` ACCEPT in INPUT chain — required for VPN access. If iptables flushed, re-add
- AWG dev access: services must bind `0.0.0.0` (not `127.0.0.1`) to be reachable via 10.99.0.1
- AWG split tunnel: only `10.99.0.0/24` routed through VPN — no full tunnel
- vless-sub: env vars `HWID`, `VLESS_SUB_URLS` required in `/opt/infra/.env`
- vless-sub image: `docker.io/xpos587/vless-sub-server:latest` — custom, not on Docker Hub
- `docker compose down --remove-orphans` destroys containers not in compose.yaml — NEVER use without checking

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

- Infra: `POSTGRES_PASSWORD`, `HWID`, `VLESS_SUB_URLS`, `CLOUDFLARE_API_TOKEN`, `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY`
- AI: `MIROFISH_LLM_API_KEY`, `MIROFISH_LLM_BASE_URL`, `MIROFISH_LLM_MODEL_NAME`, `OPENVIKING_API_KEY`, `NEO4J_PASSWORD`
- SkateLab: `DATABASE_URL`, `VALKEY_URL`, `S3_*`, `VASTAI_API_KEY`, `JWT_SECRET_KEY`, `RESEND_API_KEY`
- PostHog (Cloud): `POSTHOG_API_KEY`, `POSTHOG_HOST`, `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST`