# Dedic Dev Environment Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up isolated dev environment on dedic (176.9.0.156) for skating-biomechanics-ml with Claude Code, Headscale mesh access, and network isolation from prod.

**Architecture:** Separate Linux user `dev` owns all dev tooling and repos. Backend/frontend run **natively** (same as local dev: `task dev`). Docker only for Postgres + Valkey (same as local `infra/compose.yaml`). Headscale provides WireGuard mesh for browser access to dev previews. Prod infra (`/opt/infra`) is untouched.

**Tech Stack:** Debian Trixie, Docker CE 29.5.1, uv, bun, git, tmux 3.5a, Claude Code CLI, Headscale, Tailscale client

---

## Phase 1: Dev Workspace

### User `dev`

- Home: `/home/dev`
- Shell: `/bin/bash`
- Primary group: `dev`
- Secondary groups: `docker` (manage containers)
- NOPASSWD sudo: **none** — dev does NOT get full sudo. Only `docker` group access.
- SSH: local `~/.ssh/id_rsa_remote_nopass` pubkey → `/home/dev/.ssh/authorized_keys` (same key as admin)
- Add to `~/.ssh/config` locally: `Host dedic-dev` with `User dev`

### Tooling

| Tool | Install method | Path |
|------|---------------|------|
| git | `sudo apt install git` | `/usr/bin/git` |
| uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `~/.local/bin/uv` |
| bun | `curl -fsSL https://bun.sh/install \| bash` | `~/.bun/bin/bun` |
| tmux | Already installed (3.5a) | `/usr/bin/tmux` |
| Claude Code | `curl -fsSL https://claude.ai/install.sh \| bash` | `~/.claude/bin/claude` |

### Git Deploy Key

- Generate `ed25519` key as `dev` user: `ssh-keygen -t ed25519 -C "dedic-dev-deploy"`
- Add as deploy key to GitHub repo (read+write)
- Configure `~dev/.ssh/config`:
  ```
  Host github.com
    IdentityFile ~/.ssh/id_ed25519
    User git
  ```

### Repository

- Clone: `git clone git@github.com:Artiffusion-Inc/skating-biomechanics-ml.git /home/dev/skatelab`
- `.env.dev` for dev-specific config (separate API keys, DB credentials, ports)
- `uv sync` + `bun install` to set up dependencies

### Shell profile

Add to `/home/dev/.bashrc`:
- `export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.claude/bin:$PATH"`

---

## Phase 2: Dev Docker (Postgres + Valkey only)

### Architecture

Backend and frontend run **natively** via `task dev` — no Docker containers for app code. Docker only for databases, same pattern as local development.

```
/home/dev/skatelab/
├── docker/
│   ├── compose.yaml         ← dev Postgres + Valkey (127.0.0.1)
│   └── headscale/           ← Headscale config (Phase 3)
├── backend/                 ← uv run litestar run --port 8000 --reload (native)
├── frontend/                ← bun run dev --port 3000 (native)
└── ...
```

### docker/compose.yaml

Mirrors local `infra/compose.yaml` but with dev credentials and separate data volumes.

```yaml
name: dev

services:
  postgres:
    image: docker.io/library/postgres:17-alpine
    restart: unless-stopped
    ports:
      - "127.0.0.1:5432:5432"
    environment:
      POSTGRES_DB: skatelab
      POSTGRES_USER: skatelab
      POSTGRES_PASSWORD: skatelab_dev
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U skatelab -d skatelab"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - postgres-data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 512m

  valkey:
    image: docker.io/valkey/valkey:alpine
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - valkey-data:/data
    deploy:
      resources:
        limits:
          memory: 128m

volumes:
  postgres-data:
  valkey-data:
```

### Network isolation

- Dev compose uses default bridge network (no custom network name needed)
- Dev services bind `127.0.0.1` only — not accessible from internet
- Prod containers on `app_network` — completely separate
- Dev Docker volumes (`dev_postgres-data`, `dev_valkey-data`) — never shared with prod

### Port conflict avoidance

Dev Postgres (5432) and Valkey (6379) bind to `127.0.0.1`. Prod containers use internal Docker networking (no host port bindings). No conflicts.

### .env.dev

```env
LITESTAR_APP=app.main:create_app
VALKEY_HOST=localhost
VALKEY_PORT=6379
DATABASE_URL=postgresql+asyncpg://skatelab:skatelab_dev@localhost:5432/skatelab
JWT_SECRET_KEY=dev-secret-change-me
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
# Copy R2, Vast.ai, Sentry keys from local .env
```

---

## Phase 3: Headscale

### Architecture

```
Your laptop                           Dedic (176.9.0.156)
┌──────────┐    WireGuard     ┌──────────────────────┐
│ Tailscale │◄──────────────►│ Headscale             │
│ client    │   100.x.x.x    │ (Docker, dev compose) │
│           │                └──────────────────────┘
└──────────┘                          │
                              ┌────────┴─────────┐
                              │ Native processes  │
                              │ backend :8000     │
                              │ frontend :3000    │
                              └──────────────────┘
```

Headscale runs in Docker (dev compose). Backend/frontend run natively. Tailscale on your laptop creates a WireGuard tunnel to the server, and you access dev previews directly at `http://100.x.x.x:3000`.

### Headscale container

Add to `docker/compose.yaml`:

```yaml
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
```

### Headscale config

`docker/headscale/config/config.yaml`:
- `server_url: https://headscale.skatelab.ru`
- `listen_addr: 0.0.0.0:8080`
- `magic_dns: true`
- `base_domain: tail.skatelab.ru`
- `database: sqlite` at `/var/lib/headscale/db.sqlite`
- DERP: embedded (no external relay for single server)

### Caddy routing (prod Caddyfile)

Add to `/opt/infra/services/caddy/Caddyfile`:

```
headscale.skatelab.ru {
    reverse_proxy localhost:8080
}
```

Headscale HTTP API exposed via Caddy for `tailscale up --login-server` from any device.

### iptables

Add UDP 41641 rule:
```
ACCEPT     udp  --  0.0.0.0/0  0.0.0.0/0  udp dpt:41641
```

Persist via `/etc/iptables/rules.v4`.

### Pre-auth key

After first start:
```bash
docker exec dev-headscale-1 headscale users create michael
docker exec dev-headscale-1 headscale preauthkeys create -u michael
```

### Client setup (laptop)

```bash
tailscale up --login-server https://headscale.skatelab.ru --authkey=<key>
```

### Usage flow

1. SSH as `dev`, start databases:
   ```bash
   cd ~/skatelab/docker && docker compose up -d
   ```

2. Start dev servers (tmux or separate panes):
   ```bash
   cd ~/skatelab && task dev
   ```

3. From laptop (on tailnet):
   - `http://100.x.x.x:3000` — dev frontend
   - `http://100.x.x.x:8000/docs` — dev API docs

4. Claude Code in tmux:
   ```bash
   tmux new -s claude
   cd ~/skatelab && claude
   ```

### ACL

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
2. **Dev DBs bind 127.0.0.1** — not accessible from internet. Headscale tunnel provides access.
3. **Separate Docker volumes** — dev postgres/valkey data never touches prod paths.
4. **Headscale UDP 41641** — only public port for WireGuard. HTTP API behind Caddy.
5. **Deploy key scope** — single repo, revocable independently.
6. **admin user** — retains full sudo. dev cannot escalate.

---

## Implementation Order

1. Phase 1 (Dev Workspace) — user, tools, git, deps
2. Phase 2 (Dev Docker) — Postgres + Valkey compose
3. Phase 3 (Headscale) — container, config, Caddy route, iptables, client

---

## Not In Scope

- CI/CD pipeline (separate project)
- GPU inference on dedic (no GPU — Vast.ai Serverless)
- Production deployment changes
- Monitoring/alerting for dev services