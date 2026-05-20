# infra/CLAUDE.md — Infrastructure & Deployment

## Architecture

```
Dedic (176.9.0.156) — three Docker Compose stacks:
  /opt/infra/compose.yaml     — infra services + Caddy (owns :80/:443)
  /opt/skatelab/compose.yaml  — SkateLab prod (backend, frontend, prometheus)
  /home/dev/skatelab/docker/  — dev (postgres, valkey, headscale)

Infra Caddy proxies skatelab.ru → skatelab backend/frontend via shared network.
SkateLab shares infra postgres + valkey (separate DBs, valkey DB index 3).
```

## Files

| File | Purpose |
|------|---------|
| `Containerfile` | Multi-stage build: Python 3.11 + uv + bun, builds frontend, runs uvicorn |
| `Caddyfile` | Reverse proxy: skatelab.ru API → backend:8000, /* → frontend:3000 |
| `compose.yaml` | Local dev services: Valkey (task queue) + PostgreSQL (database) |
| `compose.prod.yaml` | Production stack: backend, frontend, prometheus. Shares infra DBs. |
| `.containerignore` | Docker build exclusion rules |

## Local Development Services

```bash
podman compose up -d    # Start Valkey + PostgreSQL
podman compose down     # Stop services
```

**Valkey**: `localhost:6379` — arq task queue
**PostgreSQL**: `localhost:5432` — SQLAlchemy async (db: `src`, user: `skatelab`)

Defaults in `compose.yaml` use env vars with `:-` fallbacks (`VALKEY_HOST_PORT`, `POSTGRES_DB`, etc.).

## Production Deploy

CI/CD (`deploy.yml`): build → push GHCR → SCP compose.prod.yaml → `docker compose up -d`.

SkateLab prod uses infra postgres (`infra-postgres-1`) and infra valkey (`infra-valkey-1:6379/3`) via shared `infra_app_network`.

## Container Build

```bash
podman build -t skatelab -f infra/Containerfile .
podman run -p 8000:8000 --env-file .env skatelab
```

Build copies `backend/`, `ml/`, `data/`, builds frontend from `frontend/`. Does **not** include `docs/`, `experiments/`, or `infra/`.

## GPU Worker (Vast.ai)

Separate container in `ml/gpu_server/Containerfile` — multi-stage, 4.9GB, no torch/timm/triton.
Image: `ghcr.io/Artiffusion-Inc/skatelab-worker:latest`

## Environment Variables

See `backend/app/config.py` for full list. Key ones:
- `DATABASE_URL` — PostgreSQL connection string
- `VALKEY_URL` — Valkey/Redis connection string
- `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` — Cloudflare R2
- `VASTAI_API_KEY` — enables remote GPU dispatch
- `JWT_SECRET` — JWT signing key
