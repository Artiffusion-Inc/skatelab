# Dedic Dev Environment Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up isolated dev environment on dedic (176.9.0.156) for skating-biomechanics-ml with Claude Code, Headscale mesh access, and Docker isolation from prod.

**Architecture:** Separate Linux user `dev` owns all dev tooling and repos. Dev services run in a separate Docker Compose (`dev-compose.yaml`) on an isolated `dev_network`. Headscale (in dev compose) provides WireGuard mesh for browser access to dev previews. Prod infra (`/opt/infra`) is untouched.

**Tech Stack:** Debian Trixie, Docker CE 29.5.1, uv, bun, git, tmux 3.5a, Claude Code CLI, Headscale, Tailscale client

---

## Phase 1: Dev Workspace

### User `dev`

- Home: `/home/dev`
- Shell: `/bin/bash`
- Primary group: `dev`
- Secondary groups: `docker` (manage containers), `ssh` (if needed)
- NOPASSWD sudo: **none** — dev does NOT get full sudo. Only `docker` group access.
- SSH: local `~/.ssh/id_ed25519` pubkey → `/home/dev/.ssh/authorized_keys`
- Add to `~/.ssh/config` locally: `Host dedic-dev` with `User dev`

### Tooling

| Tool | Install method | Path |
|------|---------------|------|
| git | `sudo apt install git` | `/usr/bin/git` |
| uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `~/.local/bin/uv` |
| bun | `curl -fsSL https://bun.sh/install \| bash` | `~/.bun/bin/bun` |
| tmux | Already installed (3.5a) | `/usr/bin/tmux` |
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` | `~/.claude/bin/claude` |
| Node.js | Bun built-in (`bun x`) or fnm | — |

### Git Deploy Key

- Generate `ed25519` key as `dev` user: `ssh-keygen -t ed25519 -C "dedic-dev-deploy"`
- Add as deploy key to GitHub repo `skating-biomechanics-ml` (read+write)
- Configure `~dev/.ssh/config`:
  ```
  Host github.com
    IdentityFile ~/.ssh/id_ed25519
    User git
  ```

### Repository

- Clone: `git clone git@github.com:Artiffusion-Inc/skating-biomechanics-ml.git /home/dev/skatelab`
- `.env.dev` for dev-specific config (separate API keys, DB credentials, ports)

### Shell profile

Add to `/home/dev/.bashrc`:
- `export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.claude/bin:$PATH"`
- `eval "$(uv shell)"` if needed

---

## Phase 2: Docker Isolation

### Architecture

```
Docker daemon (shared)
├── app_network (prod, /opt/infra/compose.yaml)
│   ├── caddy, postgres, valkey, neo4j, mirofish, ...
│   └── (19 services, unchanged)
│
└── dev_network (dev, /home/dev/skatelab/docker/dev-compose.yaml)
    ├── dev-postgres
    ├── dev-valkey
    ├── dev-frontend (bun dev --host 0.0.0.0)
    ├── dev-backend (uvicorn --reload --host 0.0.0.0)
    └── headscale
```

### dev-compose.yaml

Location: `/home/dev/skatelab/docker/dev-compose.yaml`

```yaml
name: dev

services:
  dev-postgres:
    image: docker.io/postgres:16-alpine
    restart: unless-stopped
    shm_size: 256m
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: dev_postgres_2026
    volumes:
      - ./dev-data/postgres:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 512m
    networks:
      - dev_network

  dev-valkey:
    image: docker.io/valkey/valkey:alpine
    restart: unless-stopped
    volumes:
      - ./dev-data/valkey:/data
    deploy:
      resources:
        limits:
          memory: 128m
    networks:
      - dev_network

  dev-frontend:
    # Dockerfile.dev: node:20-alpine + bun install + CMD bun dev --host 0.0.0.0
    # Create if not exists: simple hot-reload container
    build:
      context: ../frontend
      dockerfile: Dockerfile.dev
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_URL: http://dev-backend:8000
    volumes:
      - ../frontend:/app
      - /app/node_modules
    ports:
      - "127.0.0.1:3000:3000"
    deploy:
      resources:
        limits:
          memory: 512m
    networks:
      - dev_network

  dev-backend:
    # Dockerfile.dev: python:3.12-slim + uv sync + CMD uvicorn --reload --host 0.0.0.0
    # Create if not exists: simple hot-reload container
    build:
      context: ../backend
      dockerfile: Dockerfile.dev
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:dev_postgres_2026@dev-postgres/skatelab
      VALKEY_URL: redis://dev-valkey:6379/0
    volumes:
      - ../backend:/app
    ports:
      - "127.0.0.1:8000:8000"
    deploy:
      resources:
        limits:
          memory: 512m
    networks:
      - dev_network

  headscale:
    image: docker.io/headscale/headscale:latest
    restart: unless-stopped
    command: headscale serve
    volumes:
      - ./headscale/config:/etc/headscale
      - ./headscale/data:/var/lib/headscale
    ports:
      - "127.0.0.1:8080:8080"
      - "0.0.0.0:41641:41641/udp"
    deploy:
      resources:
        limits:
          memory: 256m
    networks:
      - dev_network
      - app_network

networks:
  dev_network:
    driver: bridge
  app_network:
    external: true
```

### Port bindings

All dev services bind to `127.0.0.1` only (not `0.0.0.0`):
- Frontend: `127.0.0.1:3000`
- Backend: `127.0.0.1:8000`
- Headscale HTTP: `127.0.0.1:8080`
- Headscale WireGuard: `0.0.0.0:41641/udp` (must be public for connections)

### Caddy integration

Add to prod Caddyfile (in `/opt/infra/services/caddy/Caddyfile`):

```
headscale.skatelab.ru {
    reverse_proxy headscale:8080
}
```

This allows `tailscale up --login-server https://headscale.skatelab.ru` from any device.

### iptables

Add UDP 41641 rule for WireGuard:
```
ACCEPT     udp  --  0.0.0.0/0  0.0.0.0/0  udp dpt:41641
```

Persist via `/etc/iptables/rules.v4`.

### Data volumes

All under `/home/dev/skatelab/docker/dev-data/`:
- `postgres/` — dev database
- `valkey/` — dev cache

Never shared with `/opt/infra/services/`.

---

## Phase 3: Headscale

### Setup

1. **Headscale config** at `/home/dev/skatelab/docker/headscale/config/config.yaml`:
   - `server_url: https://headscale.skatelab.ru`
   - `listen_addr: 0.0.0.0:8080`
   - `magic_dns: true`
   - `base_domain: tail.skatelab.ru`
   - `database: sqlite` at `/var/lib/headscale/db.sqlite`
   - DERP: embedded (no external relay needed for single server)

2. **Pre-auth key**: Generate after first start:
   ```bash
   docker exec dev-headscale-1 headscale preauthkeys create -u michael
   ```

3. **Local Tailscale client** (on your laptop):
   ```bash
   tailscale up --login-server https://headscale.skatelab.ru --authkey=<key>
   ```

### Usage flow

1. SSH to dedic as `dev`, start dev services:
   ```bash
   cd ~/skatelab/docker
   docker compose -f dev-compose.yaml up -d
   ```

2. From laptop (already on tailnet):
   - Open `http://dedic:3000` — dev frontend preview
   - Open `http://dedic:8000/docs` — dev backend API docs

3. Claude Code runs in tmux session on server:
   ```bash
   tmux new -s claude
   cd ~/skatelab && claude
   ```

### ACL

Minimal ACL — only your user, full access to dev services:
```json
{
  "acls": [
    {"action": "accept", "src": ["michael"], "dst": ["*:*"]}
  ]
}
```

---

## Security Considerations

1. **dev user has NO sudo** — only docker group. Cannot modify system config, iptables, or prod services.
2. **dev services bind 127.0.0.1** — not accessible from internet without Headscale.
3. **Separate Docker networks** — dev_network and app_network are isolated. Dev containers cannot reach prod DBs directly.
4. **Headscale port 41641** — only UDP needed. TCP API behind Caddy + Cloudflare.
5. **Deploy key scope** — scoped to single repo, can be revoked independently of personal SSH keys.
6. **admin user** — retains full sudo for infra management. dev user cannot escalate.

---

## Implementation Order

1. Phase 1 (Dev Workspace) — ~30 min
2. Phase 2 (Docker Isolation) — ~45 min
3. Phase 3 (Headscale) — ~30 min

Total estimated: ~2 hours.

---

## Not In Scope

- CI/CD pipeline (separate project)
- GPU inference on dedic (no GPU)
- Production deployment changes
- Monitoring/alerting for dev services
