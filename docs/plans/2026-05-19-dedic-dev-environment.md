# Dedic Dev Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up isolated dev environment on dedic (176.9.0.156) — user `dev`, native tooling (uv, bun, git, Claude Code), Docker for Postgres+Valkey only, Headscale for WireGuard mesh access.

**Architecture:** Linux user `dev` with docker group (no sudo). Backend/frontend run natively via `task dev`. Docker only for databases. Headscale in Docker for browser access to dev previews. Prod infra (`/opt/infra`) untouched.

**Tech Stack:** Debian Trixie, Docker CE 29.5.1, uv, bun, git, tmux 3.5a, Claude Code CLI, Headscale, Tailscale client

---

## Wave 1: Dev User + Tooling

### Task 1: Create `dev` user with SSH access

**Files:**

- Modify: server `/home/dev/.ssh/authorized_keys` (new)
- Modify: local `~/.ssh/config` (append `dedic-dev` host)

- [ ] **Step 1: Create user and groups on dedic**

```bash
ssh dedic "sudo useradd -m -s /bin/bash -G docker dev"
```

Verify: `ssh dedic "id dev"` → `uid=...(dev docker)`

- [ ] **Step 2: Set up SSH authorized_keys for dev user**

Copy the same public key used for admin access:

```bash
ssh dedic "sudo mkdir -p /home/dev/.ssh && sudo cp /home/admin/.ssh/authorized_keys /home/dev/.ssh/authorized_keys && sudo chown -R dev:dev /home/dev/.ssh && sudo chmod 700 /home/dev/.ssh && sudo chmod 600 /home/dev/.ssh/authorized_keys"
```

Verify: `ssh -i ~/.ssh/id_rsa_remote_nopass dev@176.9.0.156 -p 43210 "whoami"` → `dev`

- [ ] **Step 3: Add `dedic-dev` SSH config locally**

Append to `~/.ssh/config`:

```
Host dedic-dev
  Hostname 176.9.0.156
  User dev
  IdentityFile ~/.ssh/id_rsa_remote_nopass
  Port 43210
```

Verify: `ssh dedic-dev "whoami"` → `dev`

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: add dedic-dev SSH config placeholder"
```

(Note: `.ssh/config` is outside the repo, so this step is a no-op if nothing changed in the repo. Skip if nothing to commit.)

---

### Task 2: Install dev tooling (git, uv, bun, Claude Code)

**Files:**

- Modify: server `/home/dev/.bashrc` (append PATH)

- [ ] **Step 1: Install git**

```bash
ssh dedic "sudo apt install -y git"
```

Verify: `ssh dedic-dev "git --version"` → `git version 2.XX`

- [ ] **Step 2: Install uv**

```bash
ssh dedic-dev 'curl -LsSf https://astral.sh/uv/install.sh | sh'
```

Verify: `ssh dedic-dev "uv --version"` → `uv 0.X.X`

- [ ] **Step 3: Install bun**

```bash
ssh dedic-dev 'curl -fsSL https://bun.sh/install | bash'
```

Verify: `ssh dedic-dev "bun --version"` → `1.X.X`

- [ ] **Step 4: Install Claude Code**

```bash
ssh dedic-dev 'curl -fsSL https://claude.ai/install.sh | bash'
```

Verify: `ssh dedic-dev "claude --version"` (should return version string)

- [ ] **Step 5: Configure PATH in .bashrc**

```bash
ssh dedic-dev 'cat >> ~/.bashrc << ''EOF''

# Dev tooling PATH
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$HOME/.claude/bin:$PATH"
eval "$(uv shell 2>/dev/null)" 2>/dev/null || true
EOF'
```

Verify: `ssh dedic-dev 'source ~/.bashrc && echo $PATH | grep -o ".local/bin"'` → `.local/bin`

- [ ] **Step 6: Verify all tools accessible after login**

```bash
ssh dedic-dev 'source ~/.bashrc && which git uv bun claude'
```

Expected: all four tools found.

---

### Task 3: Git deploy key and repo clone

**Files:**

- Create: server `/home/dev/.ssh/id_ed25519` (new key)
- Create: server `/home/dev/.ssh/config` (SSH config for GitHub)
- Create: server `/home/dev/skatelab/` (cloned repo)

- [ ] **Step 1: Generate deploy key as dev user**

```bash
ssh dedic-dev 'ssh-keygen -t ed25519 -C "dedic-dev-deploy" -f ~/.ssh/id_ed25519 -N ""'
```

Verify: `ssh dedic-dev "ls ~/.ssh/id_ed25519.pub"` → file exists

- [ ] **Step 2: Create SSH config for GitHub**

```bash
ssh dedic-dev 'cat > ~/.ssh/config << ''EOF''
Host github.com
  IdentityFile ~/.ssh/id_ed25519
  User git
  StrictHostKeyChecking accept-new
EOF'
```

- [ ] **Step 3: Add deploy key to GitHub**

Print the public key:

```bash
ssh dedic-dev "cat ~/.ssh/id_ed25519.pub"
```

Then add as deploy key at `https://github.com/Artiffusion-Inc/skating-biomechanics-ml/settings/keys` with write access.

- [ ] **Step 4: Clone the repository**

```bash
ssh dedic-dev 'git clone git@github.com:Artiffusion-Inc/skating-biomechanics-ml.git ~/skatelab'
```

Verify: `ssh dedic-dev "ls ~/skatelab/CLAUDE.md"` → file exists

- [ ] **Step 5: Install Python dependencies**

```bash
ssh dedic-dev 'cd ~/skatelab && uv sync'
```

This will take a few minutes. Verify: `ssh dedic-dev 'cd ~/skatelab && uv run python -c "import backend"'` or similar import check.

- [ ] **Step 6: Install frontend dependencies**

```bash
ssh dedic-dev 'cd ~/skatelab/frontend && bun install'
```

Verify: `ssh dedic-dev 'cd ~/skatelab/frontend && ls node_modules/.package-lock.json'`

---

### Task 4: Dev .env file

**Files:**

- Create: server `/home/dev/skatelab/.env` (copy from local with dev-specific values)

- [ ] **Step 1: Create .env on server**

The dev .env uses the same API keys (R2, Vast.ai, Sentry) from local, but with dev-specific DB credentials matching the compose file:

```bash
ssh dedic-dev 'cat > ~/skatelab/.env << ''ENVEOF''
# Litestar CLI
LITESTAR_APP=app.main:create_app

# Valkey / Redis queue
VALKEY_HOST=localhost
VALKEY_PORT=6379
VALKEY_DB=0

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://skatelab:skatelab_dev@localhost:5432/skatelab

# JWT Authentication
JWT_SECRET_KEY=dev-secret-change-me-on-prod
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]

# Cloudflare R2 (shared with local dev)
CF_R2_ACCOUNT_ID=xpos587
CF_R2_ACCESS_KEY_ID=c3468277270e26d2921ab8445889876c
CF_R2_SECRET_ACCESS_KEY=ca67f912cd82fce272b14cf1064306fdcbdbb7b17118dafe54d0f0cbf9daa47b
CF_R2_BUCKET=skating-ml-pipeline
CF_R2_ENDPOINT_URL=https://28d6f87dc336e12d133b3886d711348d.r2.cloudflarestorage.com

# Vast.ai Serverless GPU
VASTAI_API_KEY=cd8bf38a31f51cf4769a14694f0cce44474fce9ee0c74516825c9fd9d9eb121d
VASTAI_ENDPOINT_NAME=skatelab-worker

# General
APP_WORKER_MAX_JOBS=1
APP_LOG_LEVEL=INFO
APP_TASK_TTL_SECONDS=86400

# Sentry error monitoring
SENTRY_DSN=https://36b8dd2ae195c894b1941f96a3373734@o4506004503265280.ingest.us.sentry.io/4506004505362432
SENTRY_ENVIRONMENT=development
NEXT_PUBLIC_SENTRY_DSN=https://36b8dd2ae195c894b1941f96a3373734@o4506004503265280.ingest.us.sentry.io/4506004505362432

# Dev mode — skip auth, use mock user
APP_SKIP_AUTH=true
NEXT_PUBLIC_SKIP_AUTH=true

# R2 vars for pydantic-settings
R2_ACCESS_KEY_ID=c3468277270e26d2921ab8445889876c
R2_SECRET_ACCESS_KEY=ca67f912cd82fce272b14cf1064306fdcbdbb7b17118dafe54d0f0cbf9daa47b
R2_BUCKET=skating-ml-pipeline
R2_ENDPOINT_URL=https://28d6f87dc336e12d133b3886d711348d.r2.cloudflarestorage.com
ENVEOF'
```

Verify: `ssh dedic-dev "cat ~/skatelab/.env | head -5"` → shows first 5 lines

- [ ] **Step 2: Ensure .env is in .gitignore**

```bash
ssh dedic-dev "grep -q '^\.env$' ~/skatelab/.gitignore || echo '.env already ignored'"
```

If `.env` is not in `.gitignore`, add it. But it should already be there.

---

## Wave 2: Dev Docker (Postgres + Valkey)

### Task 5: Create dev compose file

**Files:**

- Create: server `/home/dev/skatelab/docker/compose.yaml`

- [ ] **Step 1: Create docker directory**

```bash
ssh dedic-dev 'mkdir -p ~/skatelab/docker'
```

- [ ] **Step 2: Write compose.yaml**

```bash
ssh dedic-dev 'cat > ~/skatelab/docker/compose.yaml << ''COMPOSEEOF''
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
      start_period: 10s
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
      start_period: 5s
    volumes:
      - valkey-data:/data
    deploy:
      resources:
        limits:
          memory: 128m

volumes:
  postgres-data:
  valkey-data:
COMPOSEEOF'
```

Verify: `ssh dedic-dev "cat ~/skatelab/docker/compose.yaml"` → shows full file

- [ ] **Step 3: Start dev databases**

```bash
ssh dedic-dev 'cd ~/skatelab/docker && docker compose up -d'
```

Verify: `ssh dedic-dev 'docker ps --format "table {{.Names}}\t{{.Status}}"'` → shows `dev-postgres-1` and `dev-valkey-1` as healthy

- [ ] **Step 4: Run database migrations**

```bash
ssh dedic-dev 'cd ~/skatelab && uv run alembic upgrade head'
```

Verify: `ssh dedic-dev 'cd ~/skatelab && uv run python -c "from app.database import engine; print(\"DB OK\")"'` or check tables exist.

- [ ] **Step 5: Test backend starts**

```bash
ssh dedic-dev 'cd ~/skatelab/backend && uv run litestar run --port 8000 &
sleep 5
curl -s http://localhost:8000/api/v1/health | head -20
kill %1'
```

Expected: health endpoint returns 200.

---

## Wave 3: Headscale

### Task 6: Headscale container and config

**Files:**

- Create: server `/home/dev/skatelab/docker/headscale/config/config.yaml`
- Modify: server `/opt/infra/services/caddy/Caddyfile` (add headscale route)
- Modify: server `/etc/iptables/rules.v4` (add UDP 41641)

- [ ] **Step 1: Create Headscale config directory**

```bash
ssh dedic-dev 'mkdir -p ~/skatelab/docker/headscale/config ~/skatelab/docker/headscale/data'
```

- [ ] **Step 2: Write Headscale config.yaml**

```bash
ssh dedic-dev 'cat > ~/skatelab/docker/headscale/config/config.yaml << ''HSEOF''
---
log_level: info
logtail: false

server_url: https://headscale.skatelab.ru
listen_addr: 0.0.0.0:8080
metrics_listen_addr: 127.0.0.1:9090

sqlite:
  path: /var/lib/headscale/db.sqlite

dns_config:
  magic_dns: true
  base_domain: tail.skatelab.ru
  nameservers:
    - 1.1.1.1
    - 8.8.8.8

derp:
  server:
    enabled: true
    region_id: 999
    region_code: "dedic"
    region_name: "Dedic DERP"
    stun_listen_addr: "0.0.0.0:3478"
    auto_update_ip: true
  urls: []
  paths: []
  auto_update: false

database:
  type: sqlite

acme_url: https://acme-v02.api.letsencrypt.org/directory
acme_email: ""

tls_cert_path: ""
tls_key_path: ""
HSEOF'
```

Verify: `ssh dedic-dev "cat ~/skatelab/docker/headscale/config/config.yaml | head -10"` → shows config

- [ ] **Step 3: Add headscale to dev compose.yaml**

Append the headscale service to the existing compose file:

```bash
ssh dedic-dev 'cat >> ~/skatelab/docker/compose.yaml << ''HSCOMPOSE''

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
      - "0.0.0.0:3478:3478/udp"
    deploy:
      resources:
        limits:
          memory: 256m
HSCOMPOSE'
```

Verify: `ssh dedic-dev "docker compose -f ~/skatelab/docker/compose.yaml config"` → valid config with 3 services

- [ ] **Step 4: Start headscale**

```bash
ssh dedic-dev 'cd ~/skatelab/docker && docker compose up -d'
```

Verify: `ssh dedic-dev 'docker ps --format "table {{.Names}}\t{{.Status}}"'` → shows `dev-headscale-1` running

- [ ] **Step 5: Add iptables rule for WireGuard (UDP 41641)**

```bash
ssh dedic 'sudo iptables -A INPUT -p udp --dport 41641 -j ACCEPT && sudo sh -c "iptables-save > /etc/iptables/rules.v4"'
```

Verify: `ssh dedic 'sudo iptables -L INPUT -n | grep 41641'` → shows ACCEPT rule

- [ ] **Step 6: Add Caddy route for headscale.skatelab.ru**

```bash
ssh dedic 'sudo tee -a /opt/infra/services/caddy/Caddyfile > /dev/null << ''CADDYEOF''

headscale.skatelab.ru {
    reverse_proxy localhost:8080
}
CADDYEOF'
```

Reload Caddy:

```bash
ssh dedic 'sudo docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile'
```

Verify: `curl -s https://headscale.skatelab.ru/health` → returns health response from Headscale

- [ ] **Step 7: Create Headscale user and pre-auth key**

```bash
ssh dedic-dev 'docker exec dev-headscale-1 headscale users create michael'
ssh dedic-dev 'docker exec dev-headscale-1 headscale preauthkeys create -u michael -reusable'
```

Save the pre-auth key output — it's needed for client setup.

- [ ] **Step 8: Write ACL file**

```bash
ssh dedic-dev 'cat > ~/skatelab/docker/headscale/config/acl.json << ''ACLEOF''
{
  "acls": [
    {"action": "accept", "src": ["michael"], "dst": ["*:*"]}
  ]
}
ACLEOF'
```

Note: Headscale needs to be configured to use this ACL file. Add `acl_file: /etc/headscale/acl.json` to config.yaml, or update the config to point to it. Verify by restarting headscale and checking logs.

---

### Task 7: Client-side Tailscale setup

**Files:**

- Modify: local machine (install/configure Tailscale client)

- [ ] **Step 1: Install Tailscale on local machine**

On Arch Linux:

```bash
sudo pacman -S tailscale
sudo systemctl enable --now tailscaled
```

- [ ] **Step 2: Connect to Headscale**

```bash
sudo tailscale up --login-server https://headscale.skatelab.ru --authkey=<pre-auth-key-from-task-6>
```

Verify: `tailscale status` → shows connected, IP assigned (100.x.x.x)

- [ ] **Step 3: Test connectivity to dedic**

```bash
ping <tailscale-IP-of-dedic>
```

Expected: ping succeeds.

- [ ] **Step 4: Test dev preview access**

On the server, start the dev services:

```bash
ssh dedic-dev 'cd ~/skatelab/docker && docker compose up -d'
ssh dedic-dev 'cd ~/skatelab && task dev &'
```

Then from laptop, open browser to `http://<tailscale-IP>:3000`. Expected: SkateLab frontend loads.

---

## Wave 4: Verification + Cleanup

### Task 8: End-to-end verification

- [ ] **Step 1: Verify all dev containers running**

```bash
ssh dedic-dev 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
```

Expected: `dev-postgres-1`, `dev-valkey-1`, `dev-headscale-1` all healthy.

- [ ] **Step 2: Verify dev user has no sudo**

```bash
ssh dedic-dev 'sudo whoami 2>&1'
```

Expected: `Sorry, user dev may not run sudo on dedic.` or similar denial.

- [ ] **Step 3: Verify dev user CAN run docker**

```bash
ssh dedic-dev 'docker ps'
```

Expected: lists all containers (both dev and prod).

- [ ] **Step 4: Verify prod containers still healthy**

```bash
ssh dedic 'sudo docker ps --format "table {{.Names}}\t{{.Status}}"'
```

Expected: all 19 infra containers + 3 dev containers running.

- [ ] **Step 5: Verify Tailscale connectivity**

```bash
tailscale status
```

Expected: shows dedic server as connected node.

- [ ] **Step 6: Verify Claude Code works**

```bash
ssh dedic-dev 'source ~/.bashrc && claude --version'
```

Expected: returns Claude Code version string.

- [ ] **Step 7: Verify git push/pull**

```bash
ssh dedic-dev 'cd ~/skatelab && git remote -v'
```

Expected: shows `origin git@github.com:Artiffusion-Inc/skating-biomechanics-ml.git`

- [ ] **Step 8: Commit any local config changes**

```bash
git add -A && git commit -m "chore: add dev environment config files"
```

(Only if there are uncommitted changes from the plan.)

---

## Notes

- **No sudo for dev**: The `dev` user is in the `docker` group but has no sudo. This limits attack surface. Admin user (`admin`) retains full sudo for infra management.
- **Port conflicts**: Dev Postgres (5432) and Valkey (6379) bind to `127.0.0.1`. Prod containers use internal Docker networking. No conflicts.
- **Headscale DERP**: Embedded DERP server on port 3478/UDP. This is needed for WireGuard relay when direct connection fails.
- **Memory limits**: Dev containers have conservative limits (Postgres 512m, Valkey 128m, Headscale 256m) to avoid competing with prod.
- **Backup**: Dev databases are NOT in the prod backup script. This is intentional — dev data is ephemeral.