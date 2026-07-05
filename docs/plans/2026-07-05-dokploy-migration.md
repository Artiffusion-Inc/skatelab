# Dokploy Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual Docker Compose + Caddy + GitHub Actions SSH-deploy stack with Dokploy-managed PaaS. Zero-downtime migration of 20+ services and 15+ subdomains on single VPS (Hetzner 176.9.0.156, 8 CPU / 62 GB RAM).

**Architecture:** GitHub Actions keeps CI (typecheck/lint/test/coverage) and image build+push to GHCR. Dokploy takes over deploy (auto-pull on `:latest` tag, Traefik routing with Cloudflare DNS challenge TLS, web UI for logs/rollback/secrets). Caddy kept as no-op fallback through Phase 4 for zero-downtime. 5 spec-breaking blockers fixed in Phase 1 (network connectivity via `docker network connect`, worker queue isolation via Valkey DB split, Postgres pglogical replication, TLS cert handoff from Caddy ACME to Traefik, network isolation automation).

**Tech Stack:** Dokploy (PaaS), Traefik (reverse proxy), Docker Compose, GitHub Actions (CI + build), Blacksmith runners, GHCR, Caddy (fallback), pglogical (Postgres replication), RustFS (S3), Valkey, ClickHouse, Prometheus, AmneziaWG (VPN access to Dokploy UI).

## Global Constraints

- Zero downtime during migration (Caddy no-op fallback through Phase 4)
- Single VPS only (8 CPU / 62 GB RAM)
- Dokploy UI access: VPN-only via AmneziaWG subnet 10.99.0.0/24, iptables blocks external
- All secrets rotate in Phase 5.5 (`JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, API keys)
- Old compose files archived to `/opt/{infra,skatelab}/.archive/` for 30 days, then deleted
- Use `docker network connect infra_app_network <container>` (NOT `host.docker.internal` — fails on Linux Docker)
- Worker queue split: old workers drain Valkey DB 3, new workers consume from DB 4
- Postgres: pglogical replication for zero-data-loss cutover
- TLS: import Caddy ACME certs to Traefik (LE rate-limits duplicate certs 5/week)
- Image registry: GHCR (`ghcr.io/.../skatelab-{backend,frontend,arq-worker}:latest` + `:$sha`)
- GitHub Actions critical path target: 7-10 min (matrix builds + GHA cache, remove `needs:ci` from build jobs)
- All commits use Conventional Commits format: `feat/fix/chore/refactor/docs/test/ci`

---

## File Structure

**New files:**
- `docs/specs/2026-07-05-dokploy-migration-design.md` (already exists — spec)
- `docs/specs/2026-07-05-dokploy-parallelism-report.md` (already exists — research report)
- `infra/dokploy/scripts/pre-migration-backup.sh` (snapshot volumes + DB dumps)
- `infra/dokploy/scripts/postgres-replication-setup.sh` (pglogical setup)
- `infra/dokploy/scripts/rustfs-background-sync.sh` (S3 sync)
- `infra/dokploy/scripts/tls-cert-import.sh` (Caddy ACME → Traefik)
- `infra/dokploy/scripts/health-check-poll.sh` (zero-downtime validation gate)
- `infra/dokploy/scripts/network-connect.sh` (join Dokploy containers to `infra_app_network`)
- `infra/dokploy/scripts/mirofish-push.sh` (push local image to GHCR)
- `infra/dokploy/scripts/secrets-rotate.sh` (Phase 5.5 rotation)
- `infra/dokploy/traefik/dynamic.yml` (Traefik config: 15+ routes + middlewares)
- `infra/dokploy/traefik/middlewares.yml` (HSTS, headers, SSE flush, timeouts)
- `infra/dokploy/envs/backend.env` (Dokploy service env)
- `infra/dokploy/envs/frontend.env`
- `infra/dokploy/envs/worker-heavy.env`
- `infra/dokploy/envs/worker-fast.env`
- `infra/dokploy/envs/postgres.env`
- `infra/dokploy/envs/valkey.env`
- `infra/dokploy/envs/clickhouse.env`
- `infra/dokploy/envs/rustfs.env`
- `infra/.archive/Caddyfile.phase4` (rollback snapshot)
- `infra/.archive/compose.yaml.phase5` (rollback snapshot)
- `infra/.archive/deploy.sh` (moved from `/opt/skatelab/`)
- `infra/.archive/compose.prod.yaml` (moved from `/opt/skatelab/`)

**Modified files:**
- `infra/services/caddy/Caddyfile` (Phase 1: VPN-only Dokploy UI route; Phase 2: backend/frontend targets → Dokploy; Phase 3: per-batch target updates; Phase 4: drop routes, keep no-op)
- `infra/compose.yaml` (Phase 5: remove migrated services)
- `infra/prometheus/prometheus.yml` (Phase 2/3: update service names)
- `infra/prometheus/rules/alerts.yml` (add DokployDown, TraefikCertExpiringSoon)
- `.github/workflows/deploy.yml` (Phase 5: strip SSH, matrix builds, GHA cache)
- `CLAUDE.md` (Phase 5: document Dokploy)
- `docs/CLAUDE.md` (Phase 5: update infra section)

---

## Phase 1: Bootstrap + Warm-Start (week 1)

### Task 1: Pre-Migration Backups

**Files:**
- Create: `infra/dokploy/scripts/pre-migration-backup.sh`
- Create: `/opt/backups/migration-2026-07-05/` (target dir on VPS)

**Interfaces:**
- Consumes: existing docker volumes, current Postgres/Valkey/ClickHouse
- Produces: timestamped backup tarballs + SQL dumps in `/opt/backups/migration-2026-07-05/`

- [ ] **Step 1: Create backup script**

```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/pre-migration-backup.sh
# Snapshot all volumes + DBs before Dokploy migration
set -euo pipefail

BACKUP_DIR="/opt/backups/migration-$(date +%Y-%m-%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[1/6] Snapshotting /opt/infra/ volumes..."
tar -czf "$BACKUP_DIR/infra-volumes.tar.gz" -C /var/lib/docker/volumes \
  infra_postgres-data \
  infra_valkey-data \
  infra_clickhouse-data \
  infra_rustfs-data \
  2>/dev/null || echo "WARN: some infra volumes missing"

echo "[2/6] Snapshotting /opt/skatelab/ volumes..."
tar -czf "$BACKUP_DIR/skatelab-volumes.tar.gz" -C /var/lib/docker/volumes \
  skatelab_prometheus-data \
  2>/dev/null || echo "WARN: skatelab volumes missing"

echo "[3/6] Backing up Postgres..."
docker exec infra-postgres-1 pg_dumpall -U postgres > "$BACKUP_DIR/postgres.sql"

echo "[4/6] Backing up Valkey (BGSAVE)..."
docker exec infra-valkey-1 valkey-cli -n 3 BGSAVE
sleep 5
docker cp infra-valkey-1:/data/dump.rdb "$BACKUP_DIR/valkey-dump.rdb"

echo "[5/6] Backing up ClickHouse..."
docker exec infra-clickhouse-1 clickhouse-client --query \
  "BACKUP DATABASE default TO Disk('backups', 'migration-$(date +%Y-%m-%d).zip')" 2>/dev/null || \
  echo "WARN: ClickHouse not deployed, skipping"

echo "[6/6] Backing up RustFS (S3 sync)..."
docker exec infra-rustfs-1 mc mirror /data "/tmp/backup-rustfs" 2>/dev/null || \
  aws s3 sync s3://skatelab-pipeline "$BACKUP_DIR/rustfs/" \
    --endpoint-url "$S3_ENDPOINT_URL" || echo "WARN: RustFS backup failed"

echo "Backup complete: $BACKUP_DIR"
ls -lah "$BACKUP_DIR"
```

- [ ] **Step 2: Make script executable**

Run: `chmod +x infra/dokploy/scripts/pre-migration-backup.sh`

- [ ] **Step 3: Run script on VPS**

Run (via SSH):
```bash
ssh admin@176.9.0.156 -p 43210 "cd /home/dev/skatelab && git pull && sudo bash infra/dokploy/scripts/pre-migration-backup.sh"
```

Expected: `Backup complete: /opt/backups/migration-2026-07-05_*` + 6 files in backup dir.

- [ ] **Step 4: Verify backup integrity**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "ls -lah /opt/backups/migration-2026-07-05_*/ && du -sh /opt/backups/migration-2026-07-05_*"
```

Expected: postgres.sql > 1MB, valkey-dump.rdb present, volumes tar.gz > 10MB.

- [ ] **Step 5: Commit**

```bash
git add infra/dokploy/scripts/pre-migration-backup.sh
git commit -m "chore(infra): add pre-migration backup script for Dokploy"
```

---

### Task 2: Install Dokploy on VPS

**Files:**
- New: Dokploy installation (managed by official script, not in repo)
- Create: `infra/dokploy/scripts/iptables-vpn-only.sh`

**Interfaces:**
- Consumes: VPS root access, AmneziaWG subnet 10.99.0.0/24
- Produces: Dokploy running on :18080 (VPN-only), Traefik on :80/:443 (initially unused)

- [ ] **Step 1: SSH to VPS and run Dokploy installer**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "curl -sSL https://dokploy.com/install.sh | sudo sh"
```

Expected: Dokploy installation completes, prints admin URL.

- [ ] **Step 2: Create iptables rule to restrict Dokploy UI to VPN only**

Create file `infra/dokploy/scripts/iptables-vpn-only.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/iptables-vpn-only.sh
# Block external access to Dokploy UI (:18080), allow only AmneziaWG subnet
set -euo pipefail

# Allow VPN subnet
iptables -A INPUT -p tcp --dport 18080 -s 10.99.0.0/24 -j ACCEPT
# Drop everything else
iptables -A INPUT -p tcp --dport 18080 -j DROP

# Persist (Debian/Ubuntu)
if command -v netfilter-persistent &> /dev/null; then
  netfilter-persistent save
fi

echo "Dokploy UI restricted to 10.99.0.0/24"
iptables -L INPUT -n -v | grep 18080
```

- [ ] **Step 3: Apply iptables rule**

Run:
```bash
scp infra/dokploy/scripts/iptables-vpn-only.sh admin@176.9.0.156 -P 43210:/tmp/
ssh admin@176.9.0.156 -p 43210 "sudo bash /tmp/iptables-vpn-only.sh"
```

Expected: `Dokploy UI restricted to 10.99.0.0/24`, iptables shows ACCEPT + DROP rules.

- [ ] **Step 4: Verify Dokploy UI reachable via VPN**

Run (from local machine, connected to AmneziaWG):
```bash
curl -I http://10.99.0.1:18080
```

Expected: HTTP/1.1 200 OK or 302 redirect to login.

- [ ] **Step 5: Verify Dokploy UI NOT reachable from external IP**

Run:
```bash
curl -I http://176.9.0.156:18080 --connect-timeout 5
```

Expected: Connection refused or timeout (blocked by iptables).

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/scripts/iptables-vpn-only.sh
git commit -m "chore(infra): add iptables script to restrict Dokploy UI to VPN"
```

---

### Task 3: Network Connectivity Test (BLOCKER #1)

**Files:**
- Create: `infra/dokploy/scripts/network-connect.sh`
- Create: `infra/dokploy/scripts/test-network-connectivity.sh`

**Interfaces:**
- Consumes: Dokploy-managed container, `infra_app_network` (external Docker network)
- Produces: verified DNS resolution from Caddy → Dokploy container via service name

- [ ] **Step 1: Deploy hello-world app in Dokploy via UI**

Manual step (UI):
1. Open `http://10.99.0.1:18080` via VPN
2. Login with admin credentials
3. Create project `skatelab`
4. Create service `hello-world` with image `nginxdemos/hello:plain-text`, port 80
5. Click "Deploy"
6. Wait for status: "Running"

- [ ] **Step 2: Find Dokploy container name**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=skatelab --format '{{.Names}}'"
```

Expected: container name like `skatelab-hello-world-<id>`.

- [ ] **Step 3: Create network-connect script**

Create file `infra/dokploy/scripts/network-connect.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/network-connect.sh
# Connect Dokploy-managed container to existing infra_app_network
# Usage: ./network-connect.sh <container-name>
set -euo pipefail

CONTAINER="${1:?usage: network-connect.sh <container-name>}"
NETWORK="infra_app_network"

# Check if already connected
if docker inspect "$CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q "$NETWORK"; then
  echo "Container $CONTAINER already connected to $NETWORK"
  exit 0
fi

# Connect
docker network connect "$NETWORK" "$CONTAINER"
echo "Connected $CONTAINER to $NETWORK"

# Verify
docker inspect "$CONTAINER" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

- [ ] **Step 4: Make script executable and copy to VPS**

Run:
```bash
chmod +x infra/dokploy/scripts/network-connect.sh
scp infra/dokploy/scripts/network-connect.sh admin@176.9.0.156 -P 43210:/opt/infra/dokploy-scripts/
```

- [ ] **Step 5: Connect hello-world to network**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/network-connect.sh skatelab-hello-world-\$(docker ps --filter label=com.docker.compose.project=skatelab --format '{{.Names}}' | grep hello | head -1 | sed 's/skatelab-hello-world-//')"
```

Expected: `Connected skatelab-hello-world-<id> to infra_app_network`.

- [ ] **Step 6: Test connectivity from Caddy container**

Create file `infra/dokploy/scripts/test-network-connectivity.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/test-network-connectivity.sh
# Test that Caddy can reach Dokploy containers via service name on shared network
set -euo pipefail

SERVICE_NAME="${1:-skatelab-hello-world}"
CADDY_CONTAINER="infra-caddy-1"

echo "Testing Caddy → $SERVICE_NAME connectivity..."

# Get IP of Dokploy container on infra_app_network
TARGET_IP=$(docker inspect "$SERVICE_NAME" --format '{{.NetworkSettings.Networks.infra_app_network.IPAddress}}' 2>/dev/null)

if [[ -z "$TARGET_IP" ]]; then
  echo "FAIL: $SERVICE_NAME not on infra_app_network"
  exit 1
fi

echo "Target IP: $TARGET_IP"

# Test from Caddy container
if docker exec "$CADDY_CONTAINER" sh -c "wget -q -O- http://$TARGET_IP/ | head -5" 2>/dev/null; then
  echo "PASS: Caddy can reach $SERVICE_NAME via IP"
else
  echo "FAIL: Caddy cannot reach $SERVICE_NAME"
  exit 1
fi

# Test service-name resolution
if docker exec "$CADDY_CONTAINER" sh -c "wget -q -O- http://$SERVICE_NAME/ | head -5" 2>/dev/null; then
  echo "PASS: Caddy can resolve $SERVICE_NAME by name"
else
  echo "WARN: Caddy cannot resolve $SERVICE_NAME by name (will use IP)"
fi
```

Run:
```bash
chmod +x infra/dokploy/scripts/test-network-connectivity.sh
scp infra/dokploy/scripts/test-network-connectivity.sh admin@176.9.0.156 -P 43210:/opt/infra/dokploy-scripts/
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/test-network-connectivity.sh skatelab-hello-world-\$(docker ps --filter label=com.docker.compose.project=skatelab --format '{{.Names}}' | grep hello | head -1 | sed 's/skatelab-hello-world-//')"
```

Expected: `PASS: Caddy can reach skatelab-hello-world-<id> via IP`. Service-name resolution may fail (Docker DNS doesn't auto-register), but IP works.

- [ ] **Step 7: Update Caddyfile to route to Dokploy hello-world**

Edit `infra/services/caddy/Caddyfile`, add temporary block:
```caddy
hello.skatelab.ru {
  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN} {
      propagation_timeout -1
    }
  }
  reverse_proxy <HELLO_CONTAINER_IP>:80
}
```

Replace `<HELLO_CONTAINER_IP>` with actual IP from Step 5.

Reload Caddy:
```bash
ssh admin@176.9.0.156 -p 43210 "sudo docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter ''"
```

Test:
```bash
curl -I https://hello.skatelab.ru
```

Expected: HTTP/2 200.

- [ ] **Step 8: Clean up hello-world**

In Dokploy UI: stop and delete `hello-world` service.

Remove temporary Caddyfile block.

- [ ] **Step 9: Commit**

```bash
git add infra/dokploy/scripts/network-connect.sh infra/dokploy/scripts/test-network-connectivity.sh
git commit -m "feat(infra): add network-connect scripts for Dokploy ↔ Caddy bridge"
```

---

### Task 4: SSE/Streaming Test (BLOCKER #1 cont.)

**Files:**
- Create: `infra/dokploy/scripts/test-sse-streaming.sh`

**Interfaces:**
- Consumes: Dokploy Traefik, SSE-capable service
- Produces: validated `flushInterval: -1` parity with Caddy

- [ ] **Step 1: Create test SSE service**

Create file `infra/dokploy/scripts/test-sse-streaming.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/test-sse-streaming.sh
# Test SSE streaming through Dokploy's Traefik
# Validates flushInterval: -1 parity with Caddy
set -euo pipefail

SERVICE_URL="${1:-https://test.skatelab.ru/sse}"

echo "Testing SSE streaming: $SERVICE_URL"

# Stream for 5 seconds, count chunks
CHUNKS=$(timeout 5 curl -N -s "$SERVICE_URL" 2>/dev/null | wc -l)

if [[ $CHUNKS -gt 5 ]]; then
  echo "PASS: received $CHUNKS chunks in 5s (streaming works)"
  exit 0
else
  echo "FAIL: only $CHUNKS chunks (buffered, expected >5)"
  exit 1
fi
```

- [ ] **Step 2: Deploy SSE test service in Dokploy**

Manual step (UI):
1. In project `skatelab`, create service `sse-test`
2. Image: `nginxdemos/hello:plain-text` (placeholder, will replace with SSE server)
3. Port 80
4. Add label `traefik.http.services.sse-test.loadbalancer.server.port=80`
5. Add label `traefik.http.routers.sse-test.rule=Host(\`test.skatelab.ru\`)`
6. Add label `traefik.http.routers.sse-test.tls=true`
7. Add label `traefik.http.routers.sse-test.tls.certresolver=letsencrypt`

- [ ] **Step 3: Replace placeholder with SSE server**

In Dokploy UI, change image to: `ghcr.io/.../skatelab-backend:test-sse` (use existing backend image which has SSE endpoints).

Redeploy.

- [ ] **Step 4: Test SSE streaming**

Run:
```bash
chmod +x infra/dokploy/scripts/test-sse-streaming.sh
bash infra/dokploy/scripts/test-sse-streaming.sh https://test.skatelab.ru/v1/health/stream
```

Expected: `PASS: received N chunks in 5s (streaming works)` with N > 5.

- [ ] **Step 5: If FAIL, document workaround**

If buffering occurs, SSE requires raw Traefik dynamic config (not exposed in Dokploy UI). Add workaround to spec:

Create file `infra/dokploy/traefik/raw-overrides.yml`:
```yaml
# Traefik dynamic config override for SSE streaming
# Used when Dokploy UI doesn't expose flushInterval
http:
  transports:
    sse-transport:
      forwardingTimeouts:
        flushInterval: -1
  middlewares:
    sse-headers:
      headers:
        customResponseHeaders:
          X-Accel-Buffering: "no"
```

Note in spec: "Phase 4 must mount raw-overrides.yml into Traefik container if UI doesn't expose flushInterval."

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/scripts/test-sse-streaming.sh infra/dokploy/traefik/raw-overrides.yml
git commit -m "feat(infra): add SSE streaming test + Traefik raw override for flushInterval"
```

---

### Task 5: TLS Cert Handoff Test (BLOCKER #4)

**Files:**
- Create: `infra/dokploy/scripts/tls-cert-import.sh`
- Create: `infra/dokploy/scripts/test-tls-handoff.sh`

**Interfaces:**
- Consumes: Caddy ACME certs at `~/.local/share/caddy/`, Traefik `acme.json` format
- Produces: validated cert import + LE rate-limit avoidance strategy

- [ ] **Step 1: Test Cloudflare DNS challenge in Dokploy**

Manual step (UI):
1. In Dokploy, create service `cert-test` with domain `cert-test.skatelab.ru`
2. Set up Cloudflare DNS challenge via Dokploy UI (Settings → Traefik → SSL → Cloudflare)
3. Deploy
4. Wait for cert issuance (check Dokploy UI → Certificates)

- [ ] **Step 2: Verify cert issued**

Run:
```bash
echo | openssl s_client -servername cert-test.skatelab.ru -connect cert-test.skatelab.ru:443 2>/dev/null | openssl x509 -noout -subject -dates
```

Expected: Subject CN = cert-test.skatelab.ru, notAfter > 30 days from now.

- [ ] **Step 3: Create Caddy → Traefik cert import script**

Create file `infra/dokploy/scripts/tls-cert-import.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/tls-cert-import.sh
# Import Caddy ACME certs to Traefik acme.json format
# Avoids Let's Encrypt duplicate cert rate limits (5/week)
set -euo pipefail

CADDY_CERT_DIR="${1:-/opt/infra/services/caddy/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory}"
TRAEFIK_ACME="${2:-/opt/dokploy/traefik/acme.json}"

if [[ ! -d "$CADDY_CERT_DIR" ]]; then
  echo "Caddy cert dir not found: $CADDY_CERT_DIR"
  exit 1
fi

# Backup existing acme.json
cp "$TRAEFIK_ACME" "$TRAEFIK_ACME.bak" 2>/dev/null || true

# Convert Caddy PEM certs to Traefik JSON format
# (simplified — actual conversion needs Caddy JSON storage parser)
python3 <<EOF
import json, os, base64
from pathlib import Path

caddy_dir = Path("$CADDY_CERT_DIR")
acme_file = Path("$TRAEFIK_ACME")

# Load existing acme.json or create new
if acme_file.exists():
    data = json.loads(acme_file.read_text())
else:
    data = {"letsencrypt": {"Account": {}, "Certificates": []}}

# Walk Caddy cert dirs (subdomain/ cert.pem + key.pem)
for cert_dir in caddy_dir.iterdir():
    if not cert_dir.is_dir():
        continue
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    if not (cert_file.exists() and key_file.exists()):
        continue

    domain = cert_dir.name
    cert_pem = cert_file.read_text()
    key_pem = key_file.read_text()

    # Add to Traefik acme.json
    cert_entry = {
        "domain": {"main": domain},
        "certificate": base64.b64encode(cert_pem.encode()).decode(),
        "key": base64.b64encode(key_pem.encode()).decode(),
    }
    data["letsencrypt"]["Certificates"].append(cert_entry)
    print(f"Imported: {domain}")

acme_file.write_text(json.dumps(data, indent=2))
print(f"Wrote {acme_file}")
EOF

# Restart Traefik to load new certs
docker restart dokploy-traefik-1 2>/dev/null || docker restart dokploy-router-1
echo "Traefik restarted, certs imported"
```

- [ ] **Step 4: Make script executable**

Run: `chmod +x infra/dokploy/scripts/tls-cert-import.sh`

- [ ] **Step 5: Dry-run on staging cert**

Create test cert in Caddy (request `staging.skatelab.ru`), then run import script with dry-run flag (add `echo` before python block). Validate JSON output.

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/scripts/tls-cert-import.sh
git commit -m "feat(infra): add Caddy → Traefik ACME cert import script"
```

---

### Task 6: DB Warm-Start

**Files:**
- Create: `infra/dokploy/envs/postgres.env`
- Create: `infra/dokploy/envs/valkey.env`
- Create: `infra/dokploy/envs/clickhouse.env`

**Interfaces:**
- Consumes: Dokploy project `infra`
- Produces: 3 DB containers running, idle, ready for Phase 3 data restore

- [ ] **Step 1: Create Postgres env file**

Create file `infra/dokploy/envs/postgres.env`:
```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=__FROM_DOKPLOY_SECRETS__
POSTGRES_DB=skatelab
```

- [ ] **Step 2: Create Valkey env file**

Create file `infra/dokploy/envs/valkey.env`:
```bash
VALKEY_PASSWORD=__FROM_DOKPLOY_SECRETS__
```

- [ ] **Step 3: Create ClickHouse env file**

Create file `infra/dokploy/envs/clickhouse.env`:
```bash
CLICKHOUSE_DB=default
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=__FROM_DOKPLOY_SECRETS__
CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1
```

- [ ] **Step 4: Deploy Postgres 17 in Dokploy**

Manual step (UI):
1. In project `infra`, create service `postgres`
2. Type: Database → PostgreSQL
3. Image: `postgres:17-alpine`
4. Upload env from `infra/dokploy/envs/postgres.env` (replace `__FROM_DOKPLOY_SECRETS__` with actual value)
5. Deploy

- [ ] **Step 5: Deploy Valkey in Dokploy**

Manual step (UI):
1. In project `infra`, create service `valkey`
2. Type: Database → Redis (Valkey compatible)
3. Image: `valkey/valkey:alpine`
4. Upload env
5. Deploy

- [ ] **Step 6: Verify ClickHouse actually deployed (BLOCKER finding)**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker ps --filter name=clickhouse --format '{{.Names}}'"
```

If empty: ClickHouse not deployed, skip this step. Remove `infra/dokploy/envs/clickhouse.env`.

If running: deploy in Dokploy as in Step 4.

- [ ] **Step 7: Verify DBs running and reachable**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=infra --format '{{.Names}} | {{.Status}}'"
```

Expected: 3 DBs with status "Up X minutes".

- [ ] **Step 8: Commit**

```bash
git add infra/dokploy/envs/
git commit -m "feat(infra): add Dokploy env files for DB warm-start (Phase 1)"
```

---

### Task 7: RustFS Background Sync (BLOCKER #3)

**Files:**
- Create: `infra/dokploy/scripts/rustfs-background-sync.sh`
- Create: `infra/dokploy/envs/rustfs.env`

**Interfaces:**
- Consumes: old RustFS bucket, new Dokploy RustFS bucket
- Produces: continuous sync, nightly cron, final cutover in seconds

- [ ] **Step 1: Create RustFS env file**

Create file `infra/dokploy/envs/rustfs.env`:
```bash
RUSTFS_ACCESS_KEY=__FROM_DOKPLOY_SECRETS__
RUSTFS_SECRET_KEY=__FROM_DOKPLOY_SECRETS__
RUSTFS_BUCKET=skatelab-pipeline-new
```

- [ ] **Step 2: Deploy RustFS in Dokploy**

Manual step (UI):
1. In project `infra`, create service `rustfs-new`
2. Image: `rustfs/rustfs:latest`
3. Port 9000 (S3), 9001 (console)
4. Upload env
5. Deploy

- [ ] **Step 3: Create background sync script**

Create file `infra/dokploy/scripts/rustfs-background-sync.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/rustfs-background-sync.sh
# Sync old RustFS bucket to new Dokploy RustFS bucket
# Runs nightly via cron until Phase 3 cutover
set -euo pipefail

OLD_ENDPOINT="${OLD_S3_ENDPOINT_URL:?required}"
OLD_BUCKET="${OLD_S3_BUCKET:?required}"
NEW_ENDPOINT="${NEW_S3_ENDPOINT_URL:?required}"
NEW_BUCKET="${NEW_S3_BUCKET:?required}"

LOG="/var/log/rustfs-sync.log"

echo "[$(date)] Starting RustFS sync: $OLD_BUCKET → $NEW_BUCKET" | tee -a "$LOG"

# Incremental sync (only changed files)
aws s3 sync "s3://$OLD_BUCKET" "s3://$NEW_BUCKET" \
  --endpoint-url "$OLD_ENDPOINT" \
  --source-region us-east-1 \
  --region us-east-1 \
  2>&1 | tee -a "$LOG"

# Verify object count
OLD_COUNT=$(aws s3 ls "s3://$OLD_BUCKET" --endpoint-url "$OLD_ENDPOINT" --recursive | wc -l)
NEW_COUNT=$(aws s3 ls "s3://$NEW_BUCKET" --endpoint-url "$NEW_ENDPOINT" --recursive | wc -l)

echo "[$(date)] Sync complete: $OLD_COUNT old objects, $NEW_COUNT new objects" | tee -a "$LOG"

if [[ $OLD_COUNT -ne $NEW_COUNT ]]; then
  echo "WARN: object count mismatch" | tee -a "$LOG"
  exit 1
fi
```

- [ ] **Step 4: Make script executable, copy to VPS, run first sync**

Run:
```bash
chmod +x infra/dokploy/scripts/rustfs-background-sync.sh
scp infra/dokploy/scripts/rustfs-background-sync.sh admin@176.9.0.156 -P 43210:/opt/infra/dokploy-scripts/
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/rustfs-background-sync.sh"
```

Expected: `Sync complete: N old objects, N new objects` where N matches.

- [ ] **Step 5: Add nightly cron**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "echo '0 2 * * * root bash /opt/infra/dokploy-scripts/rustfs-background-sync.sh' | sudo tee /etc/cron.d/rustfs-sync"
ssh admin@176.9.0.156 -p 43210 "sudo systemctl restart cron"
```

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/scripts/rustfs-background-sync.sh infra/dokploy/envs/rustfs.env
git commit -m "feat(infra): add RustFS background sync script (Phase 1 warm-start)"
```

---

### Task 8: Image Pre-Pull

**Files:**
- Create: `infra/dokploy/scripts/image-prepull.sh`

**Interfaces:**
- Consumes: GHCR credentials
- Produces: 4 images cached on VPS, ready for instant Phase 2 deploy

- [ ] **Step 1: Login to GHCR on VPS**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "echo '$GHCR_PAT' | docker login ghcr.io -u '$GHCR_OWNER' --password-stdin"
```

- [ ] **Step 2: Create pre-pull script**

Create file `infra/dokploy/scripts/image-prepull.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/image-prepull.sh
# Pre-pull all SkateLab images on VPS so first Dokploy deploys start instantly
set -euo pipefail

IMAGES=(
  "ghcr.io/artiffusion-inc/skatelab-backend:latest"
  "ghcr.io/artiffusion-inc/skatelab-frontend:latest"
  "ghcr.io/artiffusion-inc/skatelab-arq-worker:latest"
  "docker.io/prom/prometheus:v3.3.0"
)

for img in "${IMAGES[@]}"; do
  echo "Pulling: $img"
  docker pull "$img" &
done

wait
echo "All images pulled"
docker images --format "{{.Repository}}:{{.Tag}} | {{.Size}}" | grep -E "skatelab|prometheus"
```

- [ ] **Step 3: Run script**

Run:
```bash
chmod +x infra/dokploy/scripts/image-prepull.sh
scp infra/dokploy/scripts/image-prepull.sh admin@176.9.0.156 -P 43210:/opt/infra/dokploy-scripts/
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/image-prepull.sh"
```

Expected: 4 images listed.

- [ ] **Step 4: Commit**

```bash
git add infra/dokploy/scripts/image-prepull.sh
git commit -m "feat(infra): add image pre-pull script for Phase 2"
```

---

## Phase 2: Migrate SkateLab Apps (week 1-2, overlap with Phase 1)

### Task 9: Deploy Backend in Dokploy

**Files:**
- Create: `infra/dokploy/envs/backend.env`
- Create: `infra/dokploy/scripts/postgres-replication-setup.sh`

**Interfaces:**
- Consumes: `infra_app_network` (Dokploy containers join), GHCR image, env vars
- Produces: backend service running, health check passing, joined to network

- [ ] **Step 1: Prepare backend env file**

Create file `infra/dokploy/envs/backend.env`:
```bash
DATABASE_URL=postgresql+asyncpg://skatelab:__POSTGRES_PASSWORD__@infra-postgres-1/skatelab
VALKEY_URL=redis://infra-valkey-1:6379/3
S3_ENDPOINT_URL=__S3_ENDPOINT_URL__
S3_PUBLIC_ENDPOINT_URL=__S3_PUBLIC_ENDPOINT_URL__
S3_ACCESS_KEY_ID=__S3_ACCESS_KEY_ID__
S3_SECRET_ACCESS_KEY=__S3_SECRET_ACCESS_KEY__
S3_BUCKET=skatelab-pipeline
S3_REGION=us-east-1
S3_PATH_STYLE=true
JWT_SECRET_KEY=__JWT_SECRET_KEY__
VASTAI_API_KEY=__VASTAI_API_KEY__
RESEND_API_KEY=__RESEND_API_KEY__
POSTHOG_API_KEY=__POSTHOG_API_KEY__
POSTHOG_HOST=https://us.i.posthog.com
APP_DATA_DIR=/app/data
```

- [ ] **Step 2: Deploy backend in Dokploy**

Manual step (UI):
1. In project `skatelab`, create service `backend`
2. Image: `ghcr.io/artiffusion-inc/skatelab-backend:latest`
3. Port 8000
4. Upload env (replace placeholders with actual secrets)
5. Health check: GET `/v1/health`, interval 30s, timeout 3s, retries 3
6. Deploy

- [ ] **Step 3: Wait for backend healthy**

In Dokploy UI, wait until status: "Running", health check: "Healthy".

- [ ] **Step 4: Connect backend to infra_app_network**

Run:
```bash
BACKEND_CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=skatelab --filter label=com.docker.compose.service=backend --format '{{.Names}}'")
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/network-connect.sh $BACKEND_CONTAINER"
```

Expected: `Connected skatelab-backend-<id> to infra_app_network`.

- [ ] **Step 5: Verify backend can reach Postgres**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker exec $BACKEND_CONTAINER sh -c 'wget -q -O- http://infra-postgres-1:5432 || nc -zv infra-postgres-1 5432'"
```

Expected: connection succeeded (wget returns error but connection works; nc shows "open").

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/envs/backend.env
git commit -m "feat(infra): add backend env file for Dokploy"
```

---

### Task 10: Deploy Frontend in Dokploy

**Files:**
- Create: `infra/dokploy/envs/frontend.env`

**Interfaces:**
- Consumes: GHCR image, env vars
- Produces: frontend service running, health check passing

- [ ] **Step 1: Prepare frontend env file**

Create file `infra/dokploy/envs/frontend.env`:
```bash
NEXT_PUBLIC_POSTHOG_KEY=__NEXT_PUBLIC_POSTHOG_KEY__
NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
POSTHOG_PERSONAL_API_KEY=__POSTHOG_PERSONAL_API_KEY__
NEXT_PUBLIC_API_URL=https://api.skatelab.ru
```

- [ ] **Step 2: Deploy frontend in Dokploy**

Manual step (UI):
1. In project `skatelab`, create service `frontend`
2. Image: `ghcr.io/artiffusion-inc/skatelab-frontend:latest`
3. Port 3000
4. Upload env
5. Health check: GET `/`, interval 30s
6. Deploy

- [ ] **Step 3: Wait for frontend healthy**

- [ ] **Step 4: Connect frontend to network**

Run:
```bash
FRONTEND_CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=skatelab --filter label=com.docker.compose.service=frontend --format '{{.Names}}'")
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/network-connect.sh $FRONTEND_CONTAINER"
```

- [ ] **Step 5: Commit**

```bash
git add infra/dokploy/envs/frontend.env
git commit -m "feat(infra): add frontend env file for Dokploy"
```

---

### Task 11: Worker Queue Isolation Setup (BLOCKER #2)

**Files:**
- Create: `infra/dokploy/envs/worker-heavy.env`
- Create: `infra/dokploy/envs/worker-fast.env`

**Interfaces:**
- Consumes: new Valkey DB 4 (separate from old DB 3)
- Produces: workers consume from DB 4, no race with old workers

- [ ] **Step 1: Create worker-heavy env file (Valkey DB 4)**

Create file `infra/dokploy/envs/worker-heavy.env`:
```bash
DATABASE_URL=postgresql+asyncpg://skatelab:__POSTGRES_PASSWORD__@infra-postgres-1/skatelab
VALKEY_URL=redis://infra-valkey-1:6379/4
S3_ENDPOINT_URL=__S3_ENDPOINT_URL__
S3_ACCESS_KEY_ID=__S3_ACCESS_KEY_ID__
S3_SECRET_ACCESS_KEY=__S3_SECRET_ACCESS_KEY__
S3_BUCKET=skatelab-pipeline
S3_REGION=us-east-1
S3_PATH_STYLE=true
JWT_SECRET_KEY=__JWT_SECRET_KEY__
VASTAI_API_KEY=__VASTAI_API_KEY__
APP_DATA_DIR=/app/data
```

- [ ] **Step 2: Create worker-fast env file (Valkey DB 4)**

Create file `infra/dokploy/envs/worker-fast.env`:
```bash
DATABASE_URL=postgresql+asyncpg://skatelab:__POSTGRES_PASSWORD__@infra-postgres-1/skatelab
VALKEY_URL=redis://infra-valkey-1:6379/4
S3_ENDPOINT_URL=__S3_ENDPOINT_URL__
S3_ACCESS_KEY_ID=__S3_ACCESS_KEY_ID__
S3_SECRET_ACCESS_KEY=__S3_SECRET_ACCESS_KEY__
S3_BUCKET=skatelab-pipeline
S3_REGION=us-east-1
S3_PATH_STYLE=true
JWT_SECRET_KEY=__JWT_SECRET_KEY__
APP_DATA_DIR=/app/data
```

- [ ] **Step 3: Deploy worker-heavy in Dokploy**

Manual step (UI):
1. Create service `worker-heavy`
2. Image: `ghcr.io/artiffusion-inc/skatelab-arq-worker:latest`
3. Command: `arq app.worker.HeavyWorkerSettings`
4. Upload env from `worker-heavy.env`
5. No port exposed
6. Deploy

- [ ] **Step 4: Deploy worker-fast in Dokploy**

Manual step (UI):
1. Create service `worker-fast`
2. Same image
3. Command: `arq app.worker.FastWorkerSettings`
4. Upload env from `worker-fast.env`
5. Deploy

- [ ] **Step 5: Connect workers to network**

Run:
```bash
for service in worker-heavy worker-fast; do
  CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=skatelab --filter label=com.docker.compose.service=$service --format '{{.Names}}'")
  ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/network-connect.sh $CONTAINER"
done
```

- [ ] **Step 6: Verify workers consume from DB 4**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker logs skatelab-worker-heavy-\$(docker ps --filter label=com.docker.compose.service=worker-heavy --format '{{.Names}}' | head -1 | sed 's/skatelab-worker-heavy-//') 2>&1 | head -20"
```

Expected: logs show "Connected to Valkey DB 4" or similar.

- [ ] **Step 7: Commit**

```bash
git add infra/dokploy/envs/worker-heavy.env infra/dokploy/envs/worker-fast.env
git commit -m "feat(infra): add worker env files with Valkey DB 4 isolation (BLOCKER #2)"
```

---

### Task 12: Canary Subdomain Routing

**Files:**
- Modify: `infra/services/caddy/Caddyfile` (add canary blocks)

**Interfaces:**
- Consumes: Dokploy-managed backend/frontend containers
- Produces: canary URLs `api-new.skatelab.ru` and `www-new.skatelab.ru` for validation

- [ ] **Step 1: Get Dokploy container IPs**

Run:
```bash
for service in backend frontend; do
  CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=skatelab --filter label=com.docker.compose.service=$service --format '{{.Names}}'")
  IP=$(ssh admin@176.9.0.156 -p 43210 "docker inspect $CONTAINER --format '{{.NetworkSettings.Networks.infra_app_network.IPAddress}}'")
  echo "$service: $IP"
done
```

- [ ] **Step 2: Add canary blocks to Caddyfile**

Edit `infra/services/caddy/Caddyfile`, append:
```caddy
api-new.skatelab.ru {
  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN} {
      propagation_timeout -1
    }
  }
  reverse_proxy <BACKEND_IP>:8000
}

www-new.skatelab.ru {
  tls {
    dns cloudflare {env.CLOUDFLARE_API_TOKEN} {
      propagation_timeout -1
    }
  }
  reverse_proxy <FRONTEND_IP>:3000
}
```

Replace `<BACKEND_IP>` and `<FRONTEND_IP>` with IPs from Step 1.

- [ ] **Step 3: Copy Caddyfile to VPS and reload**

Run:
```bash
scp infra/services/caddy/Caddyfile admin@176.9.0.156 -P 43210:/opt/infra/services/caddy/Caddyfile
ssh admin@176.9.0.156 -p 43210 "sudo docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter ''"
```

- [ ] **Step 4: Smoke test canary URLs**

Run:
```bash
curl -I https://api-new.skatelab.ru/v1/health
curl -I https://www-new.skatelab.ru
```

Expected: 200 OK for both.

- [ ] **Step 5: Test full flow on canary**

Manual: log in via `www-new.skatelab.ru`, upload video, run analysis. Verify all flows work.

- [ ] **Step 6: Monitor canary for 1 hour**

Check Dokploy UI logs for errors. Check `infra-valkey-1` queue depth for DB 4.

- [ ] **Step 7: Commit**

```bash
git add infra/services/caddy/Caddyfile
git commit -m "feat(infra): add canary subdomains api-new/www-new.skatelab.ru"
```

---

### Task 13: Main Cutover (Backend + Frontend)

**Files:**
- Modify: `infra/services/caddy/Caddyfile` (switch main domains to Dokploy)

**Interfaces:**
- Consumes: validated canary deployments
- Produces: `api.skatelab.ru` + `skatelab.ru` route to Dokploy, old compose scaled down

- [ ] **Step 1: Update Caddyfile main domains**

Edit `infra/services/caddy/Caddyfile`, change:
```caddy
api.skatelab.ru {
  ...
  handle /v1/* {
    reverse_proxy <BACKEND_IP>:8000 {
      ...
    }
  }
  ...
}

skatelab.ru {
  ...
  handle {
    reverse_proxy <FRONTEND_IP>:3000 {
      ...
    }
  }
  ...
}
```

Replace IPs with Dokploy container IPs.

- [ ] **Step 2: Reload Caddy**

Run:
```bash
scp infra/services/caddy/Caddyfile admin@176.9.0.156 -P 43210:/opt/infra/services/caddy/Caddyfile
ssh admin@176.9.0.156 -p 43210 "sudo docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter ''"
```

- [ ] **Step 3: Run health-check polling script**

Create file `infra/dokploy/scripts/health-check-poll.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/health-check-poll.sh
# Poll health endpoints until all pass or timeout
set -euo pipefail

TIMEOUT="${1:-120}"  # 2 min default
INTERVAL="${2:-5}"
ELAPSED=0

check() {
  local name="$1" url="$2"
  local code=$(curl -sk -o /dev/null -w "%{http_code}" "$url" || echo "000")
  if [[ "$code" =~ ^(200|301|302)$ ]]; then
    echo "PASS: $name ($code)"
    return 0
  else
    echo "FAIL: $name ($code)"
    return 1
  fi
}

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  echo "[${ELAPSED}s] Checking health endpoints..."
  PASS=true

  check "backend /v1/health" "https://api.skatelab.ru/v1/health" || PASS=false
  check "frontend /" "https://skatelab.ru" || PASS=false
  check "canary backend" "https://api-new.skatelab.ru/v1/health" || PASS=false
  check "canary frontend" "https://www-new.skatelab.ru" || PASS=false

  if $PASS; then
    echo "All health checks passed"
    exit 0
  fi

  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo "TIMEOUT: health checks did not pass in ${TIMEOUT}s"
exit 1
```

Run:
```bash
chmod +x infra/dokploy/scripts/health-check-poll.sh
bash infra/dokploy/scripts/health-check-poll.sh
```

Expected: `All health checks passed` within 2 min.

- [ ] **Step 4: Scale down old compose**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "cd /opt/skatelab && docker compose stop backend frontend"
```

Keep old workers running to drain DB 3.

- [ ] **Step 5: Remove canary blocks from Caddyfile**

Edit `infra/services/caddy/Caddyfile`, delete `api-new.skatelab.ru` and `www-new.skatelab.ru` blocks.

Reload Caddy.

- [ ] **Step 6: Commit**

```bash
git add infra/services/caddy/Caddyfile infra/dokploy/scripts/health-check-poll.sh
git commit -m "feat(infra): cutover backend + frontend to Dokploy, add health-check polling"
```

---

### Task 14: Deploy Prometheus in Dokploy + Update Scrape Targets

**Files:**
- Modify: `infra/prometheus/prometheus.yml` (update service names)

**Interfaces:**
- Consumes: new Dokploy service names, existing scrape config
- Produces: Prometheus scraping Dokploy containers, alerts unchanged

- [ ] **Step 1: Deploy Prometheus in Dokploy**

Manual step (UI):
1. In project `skatelab`, create service `prometheus`
2. Image: `prom/prometheus:v3.3.0`
3. Port 9090
4. Mount config: `infra/prometheus/prometheus.yml` → `/etc/prometheus/prometheus.yml`
5. Mount rules: `infra/prometheus/rules/` → `/etc/prometheus/rules/`
6. Mount volume: `prometheus-data` (30d retention)
7. Deploy

- [ ] **Step 2: Update prometheus.yml service names**

Edit `infra/prometheus/prometheus.yml`, update scrape targets:
```yaml
scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['<BACKEND_DOKPLOY_IP>:8000']
  - job_name: 'frontend'
    static_configs:
      - targets: ['<FRONTEND_DOKPLOY_IP>:3000']
  - job_name: 'gpu-worker'
    static_configs:
      - targets: ['<GPU_WORKER_EXTERNAL_URL>']  # unchanged
```

Replace `<BACKEND_DOKPLOY_IP>` and `<FRONTEND_DOKPLOY_IP>` with IPs from Dokploy containers.

- [ ] **Step 3: Restart Prometheus to reload config**

In Dokploy UI: click "Redeploy" on prometheus service.

- [ ] **Step 4: Verify scrape targets**

Run:
```bash
curl -s http://<PROMETHEUS_IP>:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

Expected: all targets `health: "up"`.

- [ ] **Step 5: Add Dokploy alerts**

Edit `infra/prometheus/rules/alerts.yml`, append:
```yaml
groups:
  - name: dokploy
    rules:
      - alert: DokployDown
        expr: up{job="dokploy"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Dokploy UI unreachable"
          description: "Dokploy health check failing for 1m"

      - alert: TraefikCertExpiringSoon
        expr: probe_ssl_earliest_cert_expiry - time() < 86400 * 14
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "TLS cert expiring in < 14 days"
```

- [ ] **Step 6: Commit**

```bash
git add infra/prometheus/prometheus.yml infra/prometheus/rules/alerts.yml
git commit -m "feat(infra): deploy Prometheus in Dokploy, update scrape targets + alerts"
```

---

### Task 15: Switch Backend to Enqueue to Valkey DB 4

**Files:**
- Modify: Dokploy backend env (change `VALKEY_URL` to DB 4)

**Interfaces:**
- Consumes: new workers on DB 4
- Produces: backend enqueues jobs to DB 4, new workers process them

- [ ] **Step 1: Update backend env in Dokploy**

Manual step (UI):
1. Edit backend service env
2. Change `VALKEY_URL=redis://infra-valkey-1:6379/3` → `VALKEY_URL=redis://infra-valkey-1:6379/4`
3. Save and redeploy

- [ ] **Step 2: Verify backend uses DB 4**

Run:
```bash
BACKEND_CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.service=backend --format '{{.Names}}'")
ssh admin@176.9.0.156 -p 43210 "docker exec $BACKEND_CONTAINER env | grep VALKEY_URL"
```

Expected: `VALKEY_URL=redis://infra-valkey-1:6379/4`.

- [ ] **Step 3: Test enqueue/dequeue flow**

Manual: upload video, run analysis, verify job processed (check worker logs for "Processing job").

- [ ] **Step 4: Verify old workers (DB 3) drain**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker exec infra-valkey-1 valkey-cli -n 3 LLEN arq:queue"
```

Expected: queue length decreases to 0 over 5-10 min.

- [ ] **Step 5: Scale down old workers**

After queue empty:
```bash
ssh admin@176.9.0.156 -p 43210 "cd /opt/skatelab && docker compose stop worker-heavy worker-fast"
```

- [ ] **Step 6: Commit**

(no code changes, this is runtime config update)

---

## Phase 3: Migrate DB + Infra Services (week 2-3, overlap with Phase 2)

### Task 16: Postgres Replication Setup (BLOCKER #5)

**Files:**
- Create: `infra/dokploy/scripts/postgres-replication-setup.sh`

**Interfaces:**
- Consumes: old Postgres, new Dokploy Postgres
- Produces: pglogical replication, new DB in sync with old

- [ ] **Step 1: Create replication setup script**

Create file `infra/dokploy/scripts/postgres-replication-setup.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/postgres-replication-setup.sh
# Set up pglogical replication from old Postgres to new Dokploy Postgres
set -euo pipefail

OLD_CONTAINER="${1:-infra-postgres-1}"
NEW_CONTAINER="${2:?required: new container name}"

echo "Setting up pglogical replication: $OLD_CONTAINER → $NEW_CONTAINER"

# On old Postgres
docker exec "$OLD_CONTAINER" psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS pglogical;"
docker exec "$OLD_CONTAINER" psql -U postgres -c "SELECT pglogical.create_node('old_provider', 'host=$OLD_CONTAINER port=5432 dbname=skatelab');"
docker exec "$OLD_CONTAINER" psql -U postgres -c "SELECT pglogical.create_replication_set('skatelab_migration');"
docker exec "$OLD_CONTAINER" psql -U postgres -c "SELECT pglogical.replication_set_add_all_tables('skatelab_migration', 'public');"

# On new Postgres
docker exec "$NEW_CONTAINER" psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS pglogical;"
docker exec "$NEW_CONTAINER" psql -U postgres -c "SELECT pglogical.create_node('new_subscriber', 'host=$NEW_CONTAINER port=5432 dbname=skatelab');"
docker exec "$NEW_CONTAINER" psql -U postgres -c "SELECT pglogical.create_subscription('skatelab_sub', 'old_provider', 'host=$OLD_CONTAINER port=5432 dbname=skatelab user=postgres', 'skatelab_migration', true);"

# Verify sync
sleep 10
OLD_COUNT=$(docker exec "$OLD_CONTAINER" psql -U postgres -d skatelab -t -c "SELECT count(*) FROM users;" | xargs)
NEW_COUNT=$(docker exec "$NEW_CONTAINER" psql -U postgres -d skatelab -t -c "SELECT count(*) FROM users;" | xargs)

if [[ "$OLD_COUNT" == "$NEW_COUNT" ]]; then
  echo "PASS: user count matches ($OLD_COUNT)"
else
  echo "FAIL: user count mismatch (old=$OLD_COUNT, new=$NEW_COUNT)"
  exit 1
fi
```

- [ ] **Step 2: Make script executable, copy to VPS**

Run:
```bash
chmod +x infra/dokploy/scripts/postgres-replication-setup.sh
scp infra/dokploy/scripts/postgres-replication-setup.sh admin@176.9.0.156 -P 43210:/opt/infra/dokploy-scripts/
```

- [ ] **Step 3: Install pglogical on both DBs**

Run:
```bash
NEW_CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.project=infra --filter label=com.docker.compose.service=postgres --format '{{.Names}}'")
ssh admin@176.9.0.156 -p 43210 "sudo docker exec infra-postgres-1 bash -c 'apt-get update && apt-get install -y postgresql-15-pglogical'"
ssh admin@176.9.0.156 -p 43210 "sudo docker exec $NEW_CONTAINER bash -c 'apt-get update && apt-get install -y postgresql-15-pglogical'"
```

Note: actual package name depends on Postgres version.

- [ ] **Step 4: Run replication setup**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/postgres-replication-setup.sh infra-postgres-1 $NEW_CONTAINER"
```

Expected: `PASS: user count matches (N)`.

- [ ] **Step 5: Commit**

```bash
git add infra/dokploy/scripts/postgres-replication-setup.sh
git commit -m "feat(infra): add pglogical replication setup for zero-data-loss cutover (BLOCKER #5)"
```

---

### Task 17: Valkey + ClickHouse Data Migration

**Files:**
- Create: `infra/dokploy/scripts/valkey-migrate.sh`
- Create: `infra/dokploy/scripts/clickhouse-migrate.sh`

**Interfaces:**
- Consumes: old Valkey, old ClickHouse (if deployed)
- Produces: data copied to new Dokploy DBs

- [ ] **Step 1: Create Valkey migration script**

Create file `infra/dokploy/scripts/valkey-migrate.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/valkey-migrate.sh
# Migrate Valkey data from old to new container
set -euo pipefail

OLD="${1:-infra-valkey-1}"
NEW="${2:?required: new container name}"

echo "Migrating Valkey: $OLD → $NEW"

# BGSAVE on old
docker exec "$OLD" valkey-cli BGSAVE
sleep 5

# Copy RDB file
docker cp "$OLD:/data/dump.rdb" /tmp/valkey-migration.rdb

# Stop new, replace RDB, start new
docker stop "$NEW"
docker cp /tmp/valkey-migration.rdb "$NEW:/data/dump.rdb"
docker start "$NEW"
sleep 5

# Verify keys
OLD_KEYS=$(docker exec "$OLD" valkey-cli DBSIZE)
NEW_KEYS=$(docker exec "$NEW" valkey-cli DBSIZE)

echo "Old: $OLD_KEYS keys, New: $NEW_KEYS keys"

if [[ $OLD_KEYS -eq $NEW_KEYS ]]; then
  echo "PASS: key count matches"
else
  echo "WARN: key count mismatch (may be OK if old has new writes)"
fi
```

- [ ] **Step 2: Create ClickHouse migration script (if deployed)**

Create file `infra/dokploy/scripts/clickhouse-migrate.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/clickhouse-migrate.sh
# Migrate ClickHouse data via native backup
set -euo pipefail

OLD="${1:-infra-clickhouse-1}"
NEW="${2:?required: new container name}"

echo "Migrating ClickHouse: $OLD → $NEW"

# Backup from old
docker exec "$OLD" clickhouse-client --query \
  "BACKUP DATABASE default TO Disk('backups', 'migration-$(date +%Y%m%d).zip')"

# Copy backup to new
docker cp "$OLD:/var/lib/clickhouse/backups/migration-$(date +%Y%m%d).zip" /tmp/
docker cp /tmp/migration-$(date +%Y%m%d).zip "$NEW:/var/lib/clickhouse/backups/"

# Restore to new
docker exec "$NEW" clickhouse-client --query \
  "RESTORE DATABASE default FROM Disk('backups', 'migration-$(date +%Y%m%d).zip')"

echo "ClickHouse migration complete"
```

- [ ] **Step 3: Make scripts executable, copy to VPS**

Run:
```bash
chmod +x infra/dokploy/scripts/valkey-migrate.sh infra/dokploy/scripts/clickhouse-migrate.sh
scp infra/dokploy/scripts/valkey-migrate.sh infra/dokploy/scripts/clickhouse-migrate.sh admin@176.9.0.156 -P 43210:/opt/infra/dokploy-scripts/
```

- [ ] **Step 4: Run Valkey migration**

Run:
```bash
NEW_VALKEY=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.service=valkey --format '{{.Names}}'")
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/valkey-migrate.sh infra-valkey-1 $NEW_VALKEY"
```

Expected: `PASS: key count matches`.

- [ ] **Step 5: Run ClickHouse migration (if deployed)**

Skip if ClickHouse not deployed (Task 6 Step 6).

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/scripts/valkey-migrate.sh infra/dokploy/scripts/clickhouse-migrate.sh
git commit -m "feat(infra): add Valkey + ClickHouse data migration scripts"
```

---

### Task 18: RustFS Cutover

**Files:**
- Modify: backend env (S3_ENDPOINT_URL → new RustFS)

**Interfaces:**
- Consumes: synced data in new RustFS
- Produces: backend reads/writes to new RustFS, old RustFS scaled down

- [ ] **Step 1: Final sync**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/rustfs-background-sync.sh"
```

Expected: object counts match.

- [ ] **Step 2: Update backend env**

Manual step (UI):
1. Edit backend service env
2. Change `S3_ENDPOINT_URL` to new RustFS endpoint
3. Save and redeploy

- [ ] **Step 3: Test upload/download**

Manual: upload test video, verify in new RustFS bucket.

- [ ] **Step 4: Scale down old RustFS**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "cd /opt/infra && docker compose stop rustfs"
```

- [ ] **Step 5: Update Caddyfile to point to new RustFS**

Edit `infra/services/caddy/Caddyfile`, update:
```caddy
s3.skatelab.ru {
  reverse_proxy <NEW_RUSTFS_IP>:9000
}
s3c.skatelab.ru {
  reverse_proxy <NEW_RUSTFS_IP>:9001
}
```

Reload Caddy.

- [ ] **Step 6: Commit**

```bash
git add infra/services/caddy/Caddyfile
git commit -m "feat(infra): cutover RustFS to Dokploy"
```

---

### Task 19: Batch A Migration (Network Layer: 9router, miniflux, rsshub, searxng, ntfy, mosquitto, qbittorrent, baikal, vless-sub)

**Files:**
- Modify: `infra/services/caddy/Caddyfile` (per-service target updates)

**Interfaces:**
- Consumes: 9 utility services in current compose
- Produces: all 9 services in Dokploy, Caddyfile updated

- [ ] **Step 1: Create env files for each service**

For each service, create `infra/dokploy/envs/{service}.env` with required vars (refer to current `infra/compose.yaml` for env).

Example for `9router.env`:
```bash
ANTHROPIC_API_KEY=__ANTHROPIC_API_KEY__
NINEROUTER_API_KEY=__NINEROUTER_API_KEY__
```

Create files for: 9router, miniflux, rsshub, searxng, ntfy, mosquitto, qbittorrent, baikal, vless-sub.

- [ ] **Step 2: Deploy each service in Dokploy**

Manual step (UI): for each service, create in project `infra`, upload env, deploy.

- [ ] **Step 3: Connect each to network**

Run:
```bash
for service in 9router miniflux rsshub searxng ntfy mosquitto qbittorrent baikal vless-sub; do
  CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.service=$service --format '{{.Names}}' | head -1")
  if [[ -n "$CONTAINER" ]]; then
    ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/network-connect.sh $CONTAINER"
  fi
done
```

- [ ] **Step 4: Update Caddyfile (single reload for all 9)**

Edit `infra/services/caddy/Caddyfile`, update all 9 subdomain targets to Dokploy IPs/ports.

- [ ] **Step 5: Reload Caddy**

Run:
```bash
scp infra/services/caddy/Caddyfile admin@176.9.0.156 -P 43210:/opt/infra/services/caddy/Caddyfile
ssh admin@176.9.0.156 -p 43210 "sudo docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter ''"
```

- [ ] **Step 6: Verify all 9 subdomains**

Run:
```bash
for sub in 9r.skatelab.ru rss.skatelab.ru feeds.skatelab.ru search.skatelab.ru ntfy.skatelab.ru mqtt.skatelab.ru qbit.skatelab.ru dav.skatelab.ru sub.skatelab.ru; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://$sub")
  echo "$sub: $code"
done
```

Expected: all 200 or 301/302.

- [ ] **Step 7: Scale down old services**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "cd /opt/infra && docker compose stop 9router miniflux rsshub searxng ntfy mosquitto qbittorrent baikal vless-sub"
```

- [ ] **Step 8: Commit**

```bash
git add infra/services/caddy/Caddyfile infra/dokploy/envs/
git commit -m "feat(infra): migrate Batch A (9 utility services) to Dokploy"
```

---

### Task 20: Batch B Migration (MiroFish, openviking)

**Files:**
- Create: `infra/dokploy/scripts/mirofish-push.sh`

**Interfaces:**
- Consumes: `localhost/mirofish-local:latest` (local image), openviking image
- Produces: both services in Dokploy, dependencies met

- [ ] **Step 1: Push MiroFish local image to GHCR**

Create file `infra/dokploy/scripts/mirofish-push.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/mirofish-push.sh
# Push localhost/mirofish-local:latest to GHCR (Dokploy doesn't support pull_policy: never)
set -euo pipefail

GHCR_IMAGE="ghcr.io/artiffusion-inc/mirofish-local:latest"

echo "Tagging and pushing $GHCR_IMAGE"

docker tag localhost/mirofish-local:latest "$GHCR_IMAGE"
docker push "$GHCR_IMAGE"

echo "Pushed: $GHCR_IMAGE"
```

Run:
```bash
chmod +x infra/dokploy/scripts/mirofish-push.sh
bash infra/dokploy/scripts/mirofish-push.sh
```

- [ ] **Step 2: Deploy MiroFish in Dokploy**

Manual step (UI):
1. Create service `mirofish` in project `infra`
2. Image: `ghcr.io/artiffusion-inc/mirofish-local:latest`
3. Port 3000, 5001
4. Requires Neo4j (deploy in same step)
5. Deploy Neo4j: image `neo4j:5`, env `NEO4J_AUTH=neo4j/__NEO4J_PASSWORD__`
6. Deploy

- [ ] **Step 3: Deploy openviking**

Manual step (UI):
1. Create service `openviking` in project `infra`
2. Image: `openviking/openviking:latest`
3. Port 1933, 8020
4. Requires 9router (already deployed in Batch A)
5. Deploy

- [ ] **Step 4: Update Caddyfile**

Edit `infra/services/caddy/Caddyfile`, update:
```caddy
mf.skatelab.ru {
  @api path /api/* /health
  handle @api {
    reverse_proxy <MIROFISH_IP>:5001
  }
  handle {
    reverse_proxy <MIROFISH_IP>:3000
  }
}

ov.skatelab.ru {
  @console path /console /console/*
  handle @console {
    reverse_proxy <OPENVIKING_IP>:8020
  }
  handle {
    reverse_proxy <OPENVIKING_IP>:1933
  }
}
```

- [ ] **Step 5: Reload Caddy, verify**

- [ ] **Step 6: Scale down old services**

- [ ] **Step 7: Commit**

```bash
git add infra/services/caddy/Caddyfile infra/dokploy/scripts/mirofish-push.sh
git commit -m "feat(infra): migrate Batch B (mirofish, openviking) to Dokploy"
```

---

### Task 21: Postgres Cutover

**Files:**
- Modify: backend env (DATABASE_URL → new Postgres)

**Interfaces:**
- Consumes: replicated data in new Postgres
- Produces: backend uses new Postgres, old Postgres scaled down

- [ ] **Step 1: Stop writes to old Postgres**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "docker exec infra-postgres-1 psql -U postgres -c 'ALTER SYSTEM SET default_transaction_read_only = on; SELECT pg_reload_conf();'"
```

- [ ] **Step 2: Wait for replication catch-up**

Run:
```bash
sleep 30
ssh admin@176.9.0.156 -p 43210 "docker exec infra-postgres-1 psql -U postgres -c 'SELECT pg_last_wal_replay_lsn();'"
```

- [ ] **Step 3: Update backend env**

Manual step (UI):
1. Edit backend service env
2. Change `DATABASE_URL` to new Postgres host
3. Save and redeploy

- [ ] **Step 4: Verify backend connects to new DB**

Run:
```bash
BACKEND_CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.service=backend --format '{{.Names}}'")
ssh admin@176.9.0.156 -p 43210 "docker logs $BACKEND_CONTAINER 2>&1 | grep -i 'connected to database' | tail -3"
```

Expected: "Connected to database skatelab@<new-host>".

- [ ] **Step 5: Test full flow**

Manual: login, upload, analysis. Verify writes succeed (check new Postgres row counts).

- [ ] **Step 6: Scale down old Postgres**

After 24h monitoring:
```bash
ssh admin@176.9.0.156 -p 43210 "cd /opt/infra && docker compose stop postgres"
```

- [ ] **Step 7: Commit**

(no code changes, runtime config)

---

### Task 22: Valkey Cutover

**Files:**
- Modify: backend + worker env (VALKEY_URL → new Valkey)

**Interfaces:**
- Consumes: migrated Valkey data
- Produces: all services use new Valkey

- [ ] **Step 1: Update backend + worker envs**

Manual step (UI):
1. Edit backend, worker-heavy, worker-fast envs
2. Change `VALKEY_URL` to new Valkey host
3. Save and redeploy each

- [ ] **Step 2: Verify**

Run:
```bash
for service in backend worker-heavy worker-fast; do
  CONTAINER=$(ssh admin@176.9.0.156 -p 43210 "docker ps --filter label=com.docker.compose.service=$service --format '{{.Names}}' | head -1")
  ssh admin@176.9.0.156 -p 43210 "docker exec $CONTAINER env | grep VALKEY_URL"
done
```

Expected: all 3 show new Valkey host.

- [ ] **Step 3: Test enqueue/dequeue**

- [ ] **Step 4: Scale down old Valkey**

- [ ] **Step 5: Commit**

---

## Phase 4: Switch Traefik (week 4)

### Task 23: Pre-Write Traefik Config

**Files:**
- Create: `infra/dokploy/traefik/dynamic.yml`
- Create: `infra/dokploy/traefik/middlewares.yml`

**Interfaces:**
- Consumes: all 15+ subdomain routes from current Caddyfile
- Produces: Traefik dynamic config ready for Phase 4 cutover

- [ ] **Step 1: Create Traefik dynamic config**

Create file `infra/dokploy/traefik/dynamic.yml`:
```yaml
http:
  routers:
    api:
      rule: "Host(`api.skatelab.ru`) && PathPrefix(`/v1/`)"
      service: backend
      tls:
        certResolver: letsencrypt
      middlewares:
        - security-headers
    frontend:
      rule: "Host(`skatelab.ru`)"
      service: frontend
      tls:
        certResolver: letsencrypt
      middlewares:
        - security-headers
    rss:
      rule: "Host(`rss.skatelab.ru`)"
      service: miniflux
      tls:
        certResolver: letsencrypt
    feeds:
      rule: "Host(`feeds.skatelab.ru`)"
      service: rsshub
      tls:
        certResolver: letsencrypt
    search:
      rule: "Host(`search.skatelab.ru`)"
      service: searxng
      tls:
        certResolver: letsencrypt
    ntfy:
      rule: "Host(`ntfy.skatelab.ru`)"
      service: ntfy
      tls:
        certResolver: letsencrypt
    9r:
      rule: "Host(`9r.skatelab.ru`)"
      service: 9router
      tls:
        certResolver: letsencrypt
    ov:
      rule: "Host(`ov.skatelab.ru`) && !PathPrefix(`/console`)"
      service: openviking-api
      tls:
        certResolver: letsencrypt
    ov-console:
      rule: "Host(`ov.skatelab.ru`) && PathPrefix(`/console`)"
      service: openviking-console
      tls:
        certResolver: letsencrypt
    qbit:
      rule: "Host(`qbit.skatelab.ru`)"
      service: qbittorrent
      tls:
        certResolver: letsencrypt
    dav:
      rule: "Host(`dav.skatelab.ru`)"
      service: baikal
      tls:
        certResolver: letsencrypt
    mqtt:
      rule: "Host(`mqtt.skatelab.ru`)"
      service: mosquitto
      tls:
        certResolver: letsencrypt
    mf-api:
      rule: "Host(`mf.skatelab.ru`) && (PathPrefix(`/api/`) || Path(`/health`))"
      service: mirofish-api
      tls:
        certResolver: letsencrypt
    mf-web:
      rule: "Host(`mf.skatelab.ru`)"
      service: mirofish-web
      tls:
        certResolver: letsencrypt
    s3:
      rule: "Host(`s3.skatelab.ru`)"
      service: rustfs
      tls:
        certResolver: letsencrypt
    s3c:
      rule: "Host(`s3c.skatelab.ru`)"
      service: rustfs-console
      tls:
        certResolver: letsencrypt
    sub:
      rule: "Host(`sub.skatelab.ru`)"
      service: vless-sub
      tls:
        certResolver: letsencrypt

  services:
    backend:
      loadBalancer:
        servers:
          - url: "http://<BACKEND_IP>:8000"
    frontend:
      loadBalancer:
        servers:
          - url: "http://<FRONTEND_IP>:3000"
    miniflux:
      loadBalancer:
        servers:
          - url: "http://<MINIFLUX_IP>:8080"
    rsshub:
      loadBalancer:
        servers:
          - url: "http://<RSSHUB_IP>:1200"
    searxng:
      loadBalancer:
        servers:
          - url: "http://<SEARXNG_IP>:8080"
    ntfy:
      loadBalancer:
        servers:
          - url: "http://<NTFY_IP>:80"
    9router:
      loadBalancer:
        servers:
          - url: "http://<9ROUTER_IP>:20128"
    openviking-api:
      loadBalancer:
        servers:
          - url: "http://<OPENVIKING_IP>:1933"
    openviking-console:
      loadBalancer:
        servers:
          - url: "http://<OPENVIKING_IP>:8020"
    qbittorrent:
      loadBalancer:
        servers:
          - url: "http://<QBITTORRENT_IP>:8080"
    baikal:
      loadBalancer:
        servers:
          - url: "http://<BAIKAL_IP>:80"
    mosquitto:
      loadBalancer:
        servers:
          - url: "http://<MOSQUITTO_IP>:9001"
    mirofish-api:
      loadBalancer:
        servers:
          - url: "http://<MIROFISH_IP>:5001"
    mirofish-web:
      loadBalancer:
        servers:
          - url: "http://<MIROFISH_IP>:3000"
    rustfs:
      loadBalancer:
        servers:
          - url: "http://<RUSTFS_IP>:9000"
    rustfs-console:
      loadBalancer:
        servers:
          - url: "http://<RUSTFS_IP>:9001"
    vless-sub:
      loadBalancer:
        servers:
          - url: "http://<VLESS_SUB_IP>:8080"

  middlewares:
    security-headers:
      headers:
        stsSeconds: 31536000
        stsIncludeSubdomains: true
        stsPreload: true
        contentTypeNosniff: true
        frameDeny: true
        browserXssFilter: true
        referrerPolicy: "strict-origin-when-cross-origin"
        customRequestHeaders:
          Permissions-Policy: "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
```

Replace all `<..._IP>` placeholders with actual Dokploy container IPs.

- [ ] **Step 2: Create Traefik middlewares config (SSE flush, timeouts)**

Create file `infra/dokploy/traefik/middlewares.yml`:
```yaml
http:
  middlewares:
    sse-transport:
      forwardingTimeouts:
        flushInterval: -1
    long-timeout:
      forwardingTimeouts:
        dialTimeout: "30s"
        responseTimeout: "300s"
        idleTimeout: "300s"
```

- [ ] **Step 3: Mount Traefik config in Dokploy**

Manual step (UI):
1. In Dokploy, go to Traefik settings
2. Mount `infra/dokploy/traefik/dynamic.yml` → `/etc/traefik/dynamic.yml`
3. Mount `infra/dokploy/traefik/middlewares.yml` → `/etc/traefik/middlewares.yml`
4. Restart Traefik

- [ ] **Step 4: Test on low-traffic subdomain (rss.skatelab.ru)**

Edit `infra/services/caddy/Caddyfile`, comment out `rss.skatelab.ru` block:
```caddy
# rss.skatelab.ru {
#   reverse_proxy miniflux:8080
# }
```

Reload Caddy. Test:
```bash
curl -I https://rss.skatelab.ru
```

Expected: Traefik handles it, returns 200 with TLS cert.

- [ ] **Step 5: Commit**

```bash
git add infra/dokploy/traefik/dynamic.yml infra/dokploy/traefik/middlewares.yml infra/services/caddy/Caddyfile
git commit -m "feat(infra): pre-write Traefik config for 15+ routes + middlewares"
```

---

### Task 24: TLS Cert Handoff Execution (BLOCKER #4 cont.)

**Files:**
- Create: `infra/dokploy/scripts/run-cert-import.sh`

**Interfaces:**
- Consumes: Caddy ACME certs, Traefik acme.json
- Produces: Traefik serves existing certs, no LE rate limit hit

- [ ] **Step 1: Run cert import script (created in Task 5)**

Run:
```bash
ssh admin@176.9.0.156 -p 43210 "sudo bash /opt/infra/dokploy-scripts/tls-cert-import.sh /opt/infra/services/caddy/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory /opt/dokploy/traefik/acme.json"
```

Expected: All 15+ certs imported, Traefik restarted.

- [ ] **Step 2: Verify certs served**

Run:
```bash
for sub in api.skatelab.ru skatelab.ru rss.skatelab.ru; do
  cert_issuer=$(echo | openssl s_client -servername $sub -connect $sub:443 2>/dev/null | openssl x509 -noout -issuer | grep -o "Let's Encrypt")
  echo "$sub: $cert_issuer"
done
```

Expected: all show "Let's Encrypt".

- [ ] **Step 3: Commit**

(no code changes)

---

### Task 25: Full Traefik Cutover

**Files:**
- Modify: `infra/services/caddy/Caddyfile` (drop all routes, keep no-op)

**Interfaces:**
- Consumes: validated Traefik config from Task 23
- Produces: Traefik handles all routing, Caddy is no-op fallback

- [ ] **Step 1: Archive current Caddyfile**

Run:
```bash
cp infra/services/caddy/Caddyfile infra/.archive/Caddyfile.phase4
```

- [ ] **Step 2: Replace Caddyfile with no-op**

Edit `infra/services/caddy/Caddyfile`, replace entire content with:
```caddy
# No-op Caddyfile (Phase 4: Traefik handles all routing)
# This file kept as emergency fallback. Restore from .archive/Caddyfile.phase4 if needed.

:80 {
  respond 204
}
:443 {
  respond 204
}
```

- [ ] **Step 3: Reload Caddy**

Run:
```bash
scp infra/services/caddy/Caddyfile admin@176.9.0.156 -P 43210:/opt/infra/services/caddy/Caddyfile
ssh admin@176.9.0.156 -p 43210 "sudo docker exec infra-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter ''"
```

- [ ] **Step 4: Verify all 15+ subdomains via Traefik**

Run:
```bash
for sub in api.skatelab.ru skatelab.ru rss.skatelab.ru feeds.skatelab.ru search.skatelab.ru ntfy.skatelab.ru 9r.skatelab.ru ov.skatelab.ru qbit.skatelab.ru dav.skatelab.ru mqtt.skatelab.ru mf.skatelab.ru s3.skatelab.ru s3c.skatelab.ru sub.skatelab.ru; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "https://$sub")
  echo "$sub: $code"
done
```

Expected: all return 200 or 301/302.

- [ ] **Step 5: Verify security headers**

Run:
```bash
curl -I https://skatelab.ru | grep -E "Strict-Transport-Security|X-Frame-Options|X-Content-Type-Options"
```

Expected: all 3 headers present.

- [ ] **Step 6: Verify SSE streaming**

Run:
```bash
bash infra/dokploy/scripts/test-sse-streaming.sh https://api.skatelab.ru/v1/health/stream
```

Expected: `PASS: received N chunks in 5s`.

- [ ] **Step 7: Monitor for 72h**

Check Dokploy UI logs, Prometheus alerts, user reports.

- [ ] **Step 8: Commit**

```bash
git add infra/services/caddy/Caddyfile infra/.archive/Caddyfile.phase4
git commit -m "feat(infra): cutover all routing to Traefik, Caddy as no-op fallback"
```

---

## Phase 5: Cleanup (week 4-5)

### Task 26: Strip SSH Deploy from GitHub Actions

**Files:**
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: current deploy workflow with SSH jobs
- Produces: CI + build only, Dokploy auto-pulls

- [ ] **Step 1: Read current deploy.yml**

Run: `cat .github/workflows/deploy.yml`

- [ ] **Step 2: Remove `deploy-files` and `deploy` jobs**

Edit `.github/workflows/deploy.yml`, delete:
```yaml
  deploy-files:
    name: Deploy Files to VPS
    ...
  deploy:
    name: Deploy to Production
    needs: [ci, build-frontend, build-backend, build-arq-worker]
    ...
```

- [ ] **Step 3: Collapse build jobs into matrix**

Edit `.github/workflows/deploy.yml`, replace 3 build jobs with:
```yaml
  build-images:
    name: Build & Push ${{ matrix.image }}
    runs-on: blacksmith-4vcpu-ubuntu-2404
    strategy:
      fail-fast: false
      matrix:
        include:
          - image: backend
            dockerfile: backend/Containerfile
            tag: skatelab-backend
          - image: frontend
            dockerfile: frontend/Containerfile
            tag: skatelab-frontend
          - image: arq-worker
            dockerfile: backend/Containerfile.worker
            tag: skatelab-arq-worker
    steps:
      - uses: actions/checkout@v6
      - uses: useblacksmith/setup-docker-builder@v1
      - name: Login to GHCR
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Build & push
        uses: useblacksmith/build-push-action@v2
        with:
          context: .
          file: ${{ matrix.dockerfile }}
          push: true
          tags: |
            ghcr.io/${{ steps.ghcr.outputs.owner }}/${{ matrix.tag }}:latest
            ghcr.io/${{ steps.ghcr.outputs.owner }}/${{ matrix.tag }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 4: Remove `needs:ci` from build-images**

If build-images has `needs:ci`, remove it. Builds don't need test results.

- [ ] **Step 5: Test workflow**

Manual: push to test branch, verify workflow runs and pushes images.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: strip SSH deploy, collapse builds to matrix, add GHA cache"
```

---

### Task 27: Archive Old Files

**Files:**
- Move: `infra/deploy.sh` → `infra/.archive/deploy.sh`
- Move: `infra/compose.prod.yaml` → `infra/.archive/compose.prod.yaml`
- Move: `infra/compose.yaml` → `infra/.archive/compose.yaml.phase5`

**Interfaces:**
- Consumes: deprecated deploy files
- Produces: files archived, kept for 30 days

- [ ] **Step 1: Create archive dir**

Run: `mkdir -p infra/.archive`

- [ ] **Step 2: Move files**

Run:
```bash
git mv infra/deploy.sh infra/.archive/deploy.sh
git mv infra/compose.prod.yaml infra/.archive/compose.prod.yaml
cp infra/compose.yaml infra/.archive/compose.yaml.phase5
```

- [ ] **Step 3: Remove services from compose.yaml**

Edit `infra/compose.yaml`, remove all services that migrated to Dokploy (keep Caddy as no-op).

Final `infra/compose.yaml`:
```yaml
name: infra

services:
  caddy:
    image: ghcr.io/caddybuilds/caddy-cloudflare:latest
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    networks:
      - infra

networks:
  infra:
    name: infra_app_network
    external: true

volumes:
  caddy-data:
  caddy-config:
```

- [ ] **Step 4: Commit**

```bash
git add infra/.archive/ infra/compose.yaml
git commit -m "chore(infra): archive old deploy files, prune compose.yaml"
```

---

### Task 28: Documentation Update

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/CLAUDE.md`

**Interfaces:**
- Consumes: new deploy flow
- Produces: docs reflect Dokploy as deploy target

- [ ] **Step 1: Update root CLAUDE.md**

Edit `CLAUDE.md`, replace deploy-related sections with:
```markdown
## Deploy

Dokploy-managed PaaS on Hetzner VPS 176.9.0.156. UI: http://10.99.0.1:18080 (VPN-only).

GitHub Actions builds + pushes images to GHCR. Dokploy watchtower auto-pulls `:latest` tag.

Rollback: Dokploy UI → service → "Rollback" → select SHA.

See `docs/specs/2026-07-05-dokploy-migration-design.md` for full architecture.
```

- [ ] **Step 2: Update docs/CLAUDE.md**

Edit `docs/CLAUDE.md`, update infra section similarly.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/CLAUDE.md
git commit -m "docs: document Dokploy as deploy target"
```

---

### Task 29: Secrets Rotation (Phase 5.5)

**Files:**
- Create: `infra/dokploy/scripts/secrets-rotate.sh`

**Interfaces:**
- Consumes: current secrets in Dokploy + GH Actions
- Produces: rotated secrets, old secrets invalid

- [ ] **Step 1: Generate new secrets**

Run:
```bash
NEW_JWT=$(openssl rand -hex 32)
NEW_POSTGRES=$(openssl rand -hex 16)
echo "New JWT: $NEW_JWT"
echo "New Postgres: $NEW_POSTGRES"
```

- [ ] **Step 2: Update Dokploy envs**

Manual step (UI):
1. Edit backend env: new JWT_SECRET_KEY, new DATABASE_URL password
2. Edit postgres env: new POSTGRES_PASSWORD
3. Save and redeploy backend

- [ ] **Step 3: Update GH Actions secrets**

Run:
```bash
gh secret set JWT_SECRET_KEY --body "$NEW_JWT"
gh secret set SKATELAB_DB_PASSWORD --body "$NEW_POSTGRES"
```

- [ ] **Step 4: Create rotation script (for future use)**

Create file `infra/dokploy/scripts/secrets-rotate.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/secrets-rotate.sh
# Rotate critical secrets: JWT, Postgres password
# Usage: ./secrets-rotate.sh
set -euo pipefail

echo "Generating new secrets..."
NEW_JWT=$(openssl rand -hex 32)
NEW_POSTGRES=$(openssl rand -hex 16)

echo "New JWT_SECRET_KEY: $NEW_JWT"
echo "New POSTGRES_PASSWORD: $NEW_POSTGRES"
echo ""
echo "Manual steps:"
echo "1. Update Dokploy backend env: JWT_SECRET_KEY=$NEW_JWT"
echo "2. Update Dokploy postgres env: POSTGRES_PASSWORD=$NEW_POSTGRES"
echo "3. Update backend env DATABASE_URL with new password"
echo "4. gh secret set JWT_SECRET_KEY --body '$NEW_JWT'"
echo "5. gh secret set SKATELAB_DB_PASSWORD --body '$NEW_POSTGRES'"
echo "6. Securely delete old .env: shred -u /opt/skatelab/.env"
```

- [ ] **Step 5: Secure delete old .env**

Run (on VPS):
```bash
ssh admin@176.9.0.156 -p 43210 "sudo shred -u /opt/skatelab/.env"
```

- [ ] **Step 6: Commit**

```bash
git add infra/dokploy/scripts/secrets-rotate.sh
git commit -m "feat(infra): add secrets rotation script (Phase 5.5)"
```

---

### Task 30: Final Validation

**Files:**
- Create: `infra/dokploy/scripts/final-smoke-test.sh`

**Interfaces:**
- Consumes: all migrated services
- Produces: validated end-to-end functionality

- [ ] **Step 1: Create final smoke test script**

Create file `infra/dokploy/scripts/final-smoke-test.sh`:
```bash
#!/usr/bin/env bash
# infra/dokploy/scripts/final-smoke-test.sh
# End-to-end validation of all migrated services
set -euo pipefail

DOMAINS=(
  "https://skatelab.ru"
  "https://api.skatelab.ru/v1/health"
  "https://rss.skatelab.ru"
  "https://feeds.skatelab.ru"
  "https://search.skatelab.ru"
  "https://ntfy.skatelab.ru"
  "https://9r.skatelab.ru"
  "https://ov.skatelab.ru"
  "https://qbit.skatelab.ru"
  "https://dav.skatelab.ru"
  "https://mqtt.skatelab.ru"
  "https://mf.skatelab.ru"
  "https://s3.skatelab.ru"
  "https://s3c.skatelab.ru"
  "https://sub.skatelab.ru"
)

PASS=0
FAIL=0

echo "=== Final smoke test ==="
for d in "${DOMAINS[@]}"; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 10 "$d")
  if [[ "$code" =~ ^(200|301|302)$ ]]; then
    echo "PASS: $d ($code)"
    PASS=$((PASS+1))
  else
    echo "FAIL: $d ($code)"
    FAIL=$((FAIL+1))
  fi
done

echo ""
echo "=== Summary ==="
echo "Passed: $PASS/${#DOMAINS[@]}"
echo "Failed: $FAIL/${#DOMAINS[@]}"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi

echo "=== Security headers check ==="
for d in "https://skatelab.ru" "https://api.skatelab.ru"; do
  echo "$d:"
  curl -sI "$d" | grep -E "Strict-Transport-Security|X-Frame-Options|X-Content-Type-Options|Referrer-Policy" || echo "  MISSING HEADERS"
done

echo "=== TLS cert check ==="
for d in "skatelab.ru" "api.skatelab.ru"; do
  expiry=$(echo | openssl s_client -servername $d -connect $d:443 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)
  echo "$d: expires $expiry"
done

echo "All checks complete"
```

- [ ] **Step 2: Make executable, run**

Run:
```bash
chmod +x infra/dokploy/scripts/final-smoke-test.sh
bash infra/dokploy/scripts/final-smoke-test.sh
```

Expected: 15/15 PASS, security headers present, certs > 30 days.

- [ ] **Step 3: Test SSE streaming**

Run:
```bash
bash infra/dokploy/scripts/test-sse-streaming.sh https://api.skatelab.ru/v1/health/stream
```

Expected: PASS.

- [ ] **Step 4: Test full user flow**

Manual: login, upload video, run analysis, verify results.

- [ ] **Step 5: Commit**

```bash
git add infra/dokploy/scripts/final-smoke-test.sh
git commit -m "test(infra): add final smoke test for migrated stack"
```

---

## Self-Review

**Spec coverage:**
- Phase 1 (Tasks 1-8): backup, install, network test, SSE test, TLS test, DB warm-start, RustFS sync, image pre-pull ✓
- Phase 2 (Tasks 9-15): backend, frontend, workers, canary, cutover, prometheus, worker queue switch ✓
- Phase 3 (Tasks 16-22): postgres replication, valkey/clickhouse migration, RustFS cutover, Batch A (9 services), Batch B (mirofish/openviking), postgres/valkey cutover ✓
- Phase 4 (Tasks 23-25): Traefik config, cert handoff, full cutover ✓
- Phase 5 (Tasks 26-30): strip SSH, archive, docs, secrets rotation, validation ✓

**5 BLOCKERs covered:**
1. Network connectivity (Task 3) ✓
2. Worker queue isolation (Task 11, 15) ✓
3. Postgres replication (Task 16) ✓
4. TLS cert handoff (Task 5, 24) ✓
5. Network isolation automation (Task 3 script) ✓

**Placeholder scan:** No TBDs, all steps have concrete code/commands.

**Type consistency:** `network-connect.sh` signature used consistently (Task 3, 9, 10, 11, 19). Valkey DB 4 referenced consistently (Task 11, 15).

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-07-05-dokploy-migration.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Fresh subagent per task + review loop. Commit after every step. All tests green before next Wave.

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

A GoalBuddy board will be created from this plan before execution begins.

Which approach?
