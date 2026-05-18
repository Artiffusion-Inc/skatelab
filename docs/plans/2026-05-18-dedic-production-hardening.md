# Dedic Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden production dedic server 176.9.0.156 (skatelab.ru) — 18 tasks across 4 zones, risk-ordered execution.

**Architecture:** All changes executed via SSH to remote Hetzner server. Changes are irreversible (file permissions, user accounts, iptables rules) — each task includes verification and rollback steps. Execution order follows risk analysis: zero-risk first, highest-risk (SSH admin user) last.

**Tech Stack:** Debian Trixie 13.5, Docker CE 29.5.1, iptables-persistent, systemd, Syncthing

**Server:** Hetzner dedic, 62GB RAM, 905GB disk, kernel 6.12.73

**Current state (verified 2026-05-18):**
- `.env`: 644, owner mirofish:mirofish
- `sshd_config`: PermitRootLogin prohibit-password, X11Forwarding yes, PasswordAuthentication no
- `iptables`: rules 1-2 dead podman (10.89.0.0/24), rule 3 = loopback (safe), rule 9 = port 3000 open
- `/etc/sudoers.d/mirofish-podman` exists (dead podman rule)
- `mirofish` user: uid=1000, no docker group
- `vm.swappiness` = 60, no daemon.json, no AppArmor
- Auto-reboot: commented out in 50unattended-upgrades
- Journal: no limit, 483MB used
- Valkey: no persistent volume
- 16/19 containers have no memory limits

---

## Wave 1: Zero-Risk Quick Fixes

Tasks 1-5. Independent. No service impact. All reversible.

### Task 1: Lock .env file permissions (Spec 1.1)

**Files:**
- Modify: `/opt/mirofish/.env` (permissions + ownership)

- [ ] **Step 1: Verify current permissions**

Run: `ssh dedic "ls -la /opt/mirofish/.env"`
Expected: `-rw-r--r-- 1 mirofish mirofish ... /opt/mirofish/.env`

- [ ] **Step 2: Change ownership and permissions**

```bash
ssh dedic "sudo chown root:root /opt/mirofish/.env && sudo chmod 600 /opt/mirofish/.env"
```

- [ ] **Step 3: Verify new permissions**

Run: `ssh dedic "ls -la /opt/mirofish/.env"`
Expected: `-rw------- 1 root root ... /opt/mirofish/.env`

- [ ] **Step 4: Verify docker compose still works**

```bash
ssh dedic "cd /opt/mirofish && sudo docker compose config > /dev/null && echo OK"
```
Expected: `OK` (docker compose runs as root, reads .env fine)

- [ ] **Step 5: Commit (docs only — no code changes)**

No code commit needed. Server state changed.

**Rollback:** `ssh dedic "sudo chown mirofish:mirofish /opt/mirofish/.env && sudo chmod 644 /opt/mirofish/.env"`

---

### Task 2: Remove dead sudoers file (Spec 1.3)

**Files:**
- Delete: `/etc/sudoers.d/mirofish-podman`

- [ ] **Step 1: Verify file exists and contents**

Run: `ssh dedic "sudo cat /etc/sudoers.d/mirofish-podman"`
Expected: `mirofish ALL=(ALL) NOPASSWD: /usr/bin/podman`

- [ ] **Step 2: Delete**

```bash
ssh dedic "sudo rm /etc/sudoers.d/mirofish-podman"
```

- [ ] **Step 3: Verify deleted**

Run: `ssh dedic "ls /etc/sudoers.d/mirofish-podman 2>&1"`
Expected: `No such file or directory`

**Rollback:** `ssh dedic "echo 'mirofish ALL=(ALL) NOPASSWD: /usr/bin/podman' | sudo tee /etc/sudoers.d/mirofish-podman && sudo chmod 440 /etc/sudoers.d/mirofish-podman"`

---

### Task 3: Disable X11Forwarding (Spec 1.4)

**Files:**
- Modify: `/etc/ssh/sshd_config`

- [ ] **Step 1: Verify current setting**

Run: `ssh dedic "grep X11Forwarding /etc/ssh/sshd_config"`
Expected: `X11Forwarding yes`

- [ ] **Step 2: Change to no**

```bash
ssh dedic "sudo sed -i 's/^X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config"
```

- [ ] **Step 3: Validate config**

```bash
ssh dedic "sudo sshd -t && echo VALID"
```
Expected: `VALID` (no output from sshd -t = success)

- [ ] **Step 4: Restart sshd**

```bash
ssh dedic "sudo systemctl restart sshd"
```

- [ ] **Step 5: Verify SSH still works**

Run: `ssh dedic "echo SSH_OK"`
Expected: `SSH_OK`

**Rollback:** `ssh dedic "sudo sed -i 's/^X11Forwarding no/X11Forwarding yes/' /etc/ssh/sshd_config && sudo systemctl restart sshd"`

---

### Task 4: Verify docker group policy + lock mirofish user (Spec 1.5 + 1.6)

**Files:**
- Modify: mirofish user (system account)

- [ ] **Step 1: Verify mirofish not in docker group**

Run: `ssh dedic "id mirofish"`
Expected: `uid=1000(mirofish) gid=1000(mirofish) groups=1000(mirofish)` — no docker group

- [ ] **Step 2: Lock mirofish user + disable shell**

```bash
ssh dedic "sudo usermod -L mirofish && sudo usermod -s /usr/sbin/nologin mirofish"
```

- [ ] **Step 3: Verify locked**

Run: `ssh dedic "sudo passwd -S mirofish && sudo getent passwd mirofish | cut -d: -f7"`
Expected: `mirofish L ...` (L = locked) and `/usr/sbin/nologin`

**Rollback:** `ssh dedic "sudo usermod -U mirofish && sudo usermod -s /bin/bash mirofish"`

---

### Task 5: Add Valkey persistent mount (Spec 1.7)

**Files:**
- Modify: `/opt/mirofish/compose.yaml` (valkey section, ~line 49-53)
- Create: `/opt/mirofish/services/valkey/data/` (directory on server)

- [ ] **Step 1: Create data directory on server**

```bash
ssh dedic "sudo mkdir -p /opt/mirofish/services/valkey/data"
```

- [ ] **Step 2: Edit compose.yaml — add volume to valkey**

Current (lines 49-53):
```yaml
  valkey:
    image: docker.io/valkey/valkey:alpine
    restart: unless-stopped
    networks:
      - app_network
```

Replace with:
```yaml
  valkey:
    image: docker.io/valkey/valkey:alpine
    restart: unless-stopped
    volumes:
      - ./services/valkey/data:/data
    networks:
      - app_network
```

```bash
ssh dedic "sudo sed -i '/valkey:alpine/,/app_network/ { /restart:unless-stopped/a\\    volumes:\\n      - ./services/valkey/data:/data }' /opt/mirofish/compose.yaml"
```

If sed is unreliable, use a Python one-liner or manual edit via `sudo nano`.

- [ ] **Step 3: Recreate valkey container**

```bash
ssh dedic "cd /opt/mirofish && sudo docker compose up -d valkey"
```

- [ ] **Step 4: Verify volume mounted**

Run: `ssh dedic "sudo docker inspect mirofish-valkey-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'"`
Expected: line containing `/opt/mirofish/services/valkey/data -> /data`

**Rollback:** Remove volumes section from compose.yaml, `sudo docker compose up -d valkey`

---

## Wave 2: Docker + Firewall Hardening

Tasks 6-9. Moderate risk. iptables changes require backup. daemon.json requires docker restart.

### Task 6: iptables cleanup — atomic (Spec 3.2 + 3.3)

**Files:**
- Modify: iptables INPUT chain
- Modify: `/etc/iptables/rules.v4`

**CRITICAL:** Keep active SSH session. Do NOT close terminal after iptables changes until verified.

- [ ] **Step 1: Backup current rules**

```bash
ssh dedic "sudo iptables-save > /etc/iptables/rules.v4.bak.\$(date +%s)"
```

- [ ] **Step 2: Verify rule 3 is loopback (CONFIRMED: it is `-i lo`)**

Run: `ssh dedic "sudo iptables -L INPUT -v -n --line-numbers | head -5"`
Expected: Rule 3 has `lo` in the `in` column — this is safe loopback, do NOT delete.

- [ ] **Step 3: Delete podman subnet rules (by specification, not line number)**

```bash
ssh dedic "sudo iptables -D INPUT -s 10.89.0.0/24 -j ACCEPT && sudo iptables -D INPUT -d 10.89.0.0/24 -j ACCEPT"
```

- [ ] **Step 4: Delete port 3000 rule**

```bash
ssh dedic "sudo iptables -D INPUT -p tcp --dport 3000 -j ACCEPT"
```

- [ ] **Step 5: Save rules**

```bash
ssh dedic "sudo iptables-save > /etc/iptables/rules.v4"
```

- [ ] **Step 6: Verify SSH still works**

Run: `ssh dedic "echo SSH_OK"`
Expected: `SSH_OK`

- [ ] **Step 7: Verify rules look correct**

Run: `ssh dedic "sudo iptables -L INPUT -n --line-numbers"`
Expected: No 10.89.0.0/24 rules, no port 3000 rule, loopback rule still present, SSH (22) + HTTP (80) + HTTPS (443) rules present.

**Rollback:** `ssh dedic "sudo iptables-restore < /etc/iptables/rules.v4.bak.*"`

---

### Task 7: Create daemon.json + enable live-restore (Spec 3.1)

**Files:**
- Create: `/etc/docker/daemon.json`

**IMPORTANT:** First docker restart with live-restore WILL stop all containers briefly (live-restore activates AFTER daemon starts). Containers will auto-restart with `unless-stopped` policy. Expect ~30s downtime.

- [ ] **Step 1: Verify no daemon.json exists**

Run: `ssh dedic "cat /etc/docker/daemon.json 2>&1"`
Expected: `No such file or directory`

- [ ] **Step 2: Create daemon.json**

```bash
ssh dedic "sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
  \"log-driver\": \"json-file\",
  \"log-opts\": {
    \"max-size\": \"50m\",
    \"max-file\": \"5\"
  },
  \"live-restore\": true
}
EOF"
```

- [ ] **Step 3: Validate JSON syntax**

```bash
ssh dedic "python3 -m json.tool /etc/docker/daemon.json && echo JSON_VALID"
```
Expected: `JSON_VALID`

- [ ] **Step 4: Restart Docker (containers will briefly stop, then restart)**

```bash
ssh dedic "sudo systemctl restart docker"
```

Wait ~30s, then:

```bash
ssh dedic "sudo docker ps --format 'table {{.Names}}\t{{.Status}}' | head -25"
```
Expected: All 19 containers running (some may show "health: starting" — wait for healthy).

- [ ] **Step 5: Verify live-restore is active**

Run: `ssh dedic "sudo docker info --format '{{.LiveRestoreEnabled}}'"`
Expected: `true`

- [ ] **Step 6: Verify log rotation config applied**

Run: `ssh dedic "sudo docker info --format '{{.Driver}} {{.DriverStatus}}'"`
Expected: `json-file` with max-size/max-file visible in status.

**Rollback:** `ssh dedic "sudo rm /etc/docker/daemon.json && sudo systemctl restart docker"`

---

### Task 8: Install AppArmor (Spec 3.4)

**Files:**
- Install: `apparmor`, `apparmor-profiles` (apt)

**NOTE:** Profile `docker-default` only applied on container CREATE (next `docker compose up` or recreate), not on running containers. Safe to install now.

- [ ] **Step 1: Install AppArmor**

```bash
ssh dedic "sudo apt install -y apparmor apparmor-profiles"
```

- [ ] **Step 2: Verify AppArmor is active**

Run: `ssh dedic "sudo aa-status --enabled && echo ENABLED || echo DISABLED"`
Expected: `ENABLED`

- [ ] **Step 3: Check no containers broke (existing containers unaffected)**

```bash
ssh dedic "sudo docker ps --format 'table {{.Names}}\t{{.Status}}' | head -5"
```
Expected: Same as before — all running.

**Rollback:** `ssh dedic "sudo apt purge -y apparmor apparmor-profiles && sudo apt autoremove -y"`

---

### Task 9: Add memory limits to all containers + set swappiness (Spec 4.1)

**Files:**
- Modify: `/opt/mirofish/compose.yaml` (add deploy.resources.limits to 13 services)
- Create: `/etc/sysctl.d/99-hardening.conf`

**Phase 1: Memory limits**

- [ ] **Step 1: Add memory limits to compose.yaml**

Services that already have limits (do NOT change):
- windmill_worker: 1536M (line ~173)
- 9router: 1G (line ~335)
- cadvisor: 256M (line ~201)

Services needing new limits — add `deploy.resources.limits.memory` under each service:

```yaml
  postgres:
    ...
    deploy:
      resources:
        limits:
          memory: 2G

  neo4j:
    ...
    deploy:
      resources:
        limits:
          memory: 4G

  mirofish:
    ...
    deploy:
      resources:
        limits:
          memory: 4G

  windmill_server:
    ...
    deploy:
      resources:
        limits:
          memory: 2G

  searxng:
    ...
    deploy:
      resources:
        limits:
          memory: 1G

  valkey:
    ...
    deploy:
      resources:
        limits:
          memory: 512M

  miniflux:
    ...
    deploy:
      resources:
        limits:
          memory: 512M

  rsshub:
    ...
    deploy:
      resources:
        limits:
          memory: 512M

  caddy:
    ...
    deploy:
      resources:
        limits:
          memory: 256M

  ntfy:
    ...
    deploy:
      resources:
        limits:
          memory: 256M

  syncthing:
    ...
    deploy:
      resources:
        limits:
          memory: 512M

  qbittorrent:
    ...
    deploy:
      resources:
        limits:
          memory: 512M

  baikal:
    ...
    deploy:
      resources:
        limits:
          memory: 256M

  mosquitto:
    ...
    deploy:
      resources:
        limits:
          memory: 128M

  tor:
    ...
    deploy:
      resources:
        limits:
          memory: 128M
```

Edit on server:
```bash
ssh dedic "sudo nano /opt/mirofish/compose.yaml"
```

Or use sed/python for programmatic edit. Manual edit is safest for YAML.

- [ ] **Step 2: Validate compose config**

```bash
ssh dedic "cd /opt/mirofish && sudo docker compose config > /dev/null && echo VALID"
```
Expected: `VALID`

- [ ] **Step 3: Apply changes (recreates containers with limits)**

```bash
ssh dedic "cd /opt/mirofish && sudo docker compose up -d"
```

- [ ] **Step 4: Verify limits applied**

```bash
ssh dedic "sudo docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}' | head -25"
```
Expected: All containers show memory usage, none exceeding their limits.

**Phase 2: Swappiness**

- [ ] **Step 5: Set swappiness**

```bash
ssh dedic "echo 10 | sudo tee /proc/sys/vm/swappiness"
```

- [ ] **Step 6: Persist swappiness**

```bash
ssh dedic "echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-hardening.conf"
```

- [ ] **Step 7: Verify**

Run: `ssh dedic "sysctl vm.swappiness"`
Expected: `vm.swappiness = 10`

**Rollback (limits):** Remove deploy sections from compose.yaml, `docker compose up -d`
**Rollback (swappiness):** `ssh dedic "echo 60 | sudo tee /proc/sys/vm/swappiness && sudo rm /etc/sysctl.d/99-hardening.conf"`

---

## Wave 3: System Hardening

Tasks 10-11. Low risk. Independent.

### Task 10: Set journal size limit (Spec 4.3)

**Files:**
- Modify: `/etc/systemd/journald.conf`

- [ ] **Step 1: Verify current state**

Run: `ssh dedic "journalctl --disk-usage"`
Expected: `Archived and active journals take up 483M...`

- [ ] **Step 2: Set SystemMaxUse**

```bash
ssh dedic "sudo sed -i 's/^#SystemMaxUse=/SystemMaxUse=2G/' /etc/systemd/journald.conf"
```

If the line doesn't match (commented differently):
```bash
ssh dedic "echo 'SystemMaxUse=2G' | sudo tee -a /etc/systemd/journald.conf"
```

- [ ] **Step 3: Restart journald**

```bash
ssh dedic "sudo systemctl restart systemd-journald"
```

- [ ] **Step 4: Verify**

Run: `ssh dedic "journalctl --disk-usage"`
Expected: Shows `2G` as max, current usage ≤ 483M.

**Rollback:** `ssh dedic "sudo sed -i 's/^SystemMaxUse=2G/#SystemMaxUse=/' /etc/systemd/journald.conf && sudo systemctl restart systemd-journald"`

---

### Task 11: Add health checks where missing (Spec 4.2 prerequisite)

**Files:**
- Modify: `/opt/mirofish/compose.yaml`

Services that already have health checks: postgres, neo4j, tor, cadvisor.

Services needing health checks — add to compose.yaml:

```yaml
  valkey:
    ...
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  mirofish:
    ...
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:5001/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  caddy:
    ...
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Also add missing `depends_on` with `condition: service_healthy`:

```yaml
  mirofish:
    depends_on:
      neo4j:
        condition: service_healthy

  windmill_server:
    depends_on:
      postgres:
        condition: service_healthy
      valkey:
        condition: service_healthy

  windmill_worker:
    depends_on:
      postgres:
        condition: service_healthy
      valkey:
        condition: service_healthy
```

- [ ] **Step 1: Edit compose.yaml — add health checks and depends_on**

```bash
ssh dedic "sudo nano /opt/mirofish/compose.yaml"
```

Add the health checks and depends_on shown above.

- [ ] **Step 2: Validate config**

```bash
ssh dedic "cd /opt/mirofish && sudo docker compose config > /dev/null && echo VALID"
```
Expected: `VALID`

- [ ] **Step 3: Apply**

```bash
ssh dedic "cd /opt/mirofish && sudo docker compose up -d"
```

- [ ] **Step 4: Verify health checks working**

```bash
ssh dedic "sudo docker ps --format 'table {{.Names}}\t{{.Status}}'"
```
Expected: valkey, mirofish, caddy show "healthy" after 30-60s.

**Rollback:** Remove added healthcheck/depends_on sections, `docker compose up -d`

---

## Wave 4: Backups

Tasks 12-14. Depends on Wave 2 (iptables fixed, memory limits set).

### Task 12: Deploy backup script (Spec 2.1)

**Files:**
- Create: `/usr/local/bin/backup-dbs.sh`
- Create: `/opt/mirofish/backups/{postgres,neo4j,config}`

- [ ] **Step 1: Create backup directories**

```bash
ssh dedic "sudo mkdir -p /opt/mirofish/backups/{postgres,neo4j,config}"
```

- [ ] **Step 2: Write backup script**

```bash
ssh dedic "sudo tee /usr/local/bin/backup-dbs.sh > /dev/null << 'SCRIPT'
#!/bin/bash
set -uo pipefail
BACKUP_DIR=\"/opt/mirofish/backups\"
DATE=\$(date +%Y-%m-%d_%H%M)
FAILED=0

mkdir -p \"\$BACKUP_DIR/postgres\" \"\$BACKUP_DIR/neo4j\" \"\$BACKUP_DIR/config\"

# Postgres (hot backup, no downtime)
if docker exec mirofish-postgres-1 pg_dumpall -U postgres | \\
  gzip > \"\$BACKUP_DIR/postgres/pg_dumpall_\${DATE}.sql.gz\"; then
  gunzip -t \"\$BACKUP_DIR/postgres/pg_dumpall_\${DATE}.sql.gz\"
  echo \"[\$DATE] postgres: OK\"
else
  echo \"[\$DATE] postgres: FAILED\" >&2
  FAILED=1
fi

# Neo4j (requires stop -> dump -> start, ~60s downtime)
docker exec mirofish-neo4j-1 neo4j-admin database stop neo4j
if docker exec mirofish-neo4j-1 neo4j-admin database dump neo4j \\
  --to-stdout | gzip > \"\$BACKUP_DIR/neo4j/neo4j_\${DATE}.dump.gz\"; then
  gunzip -t \"\$BACKUP_DIR/neo4j/neo4j_\${DATE}.dump.gz\"
  echo \"[\$DATE] neo4j: OK\"
else
  echo \"[\$DATE] neo4j: FAILED\" >&2
  FAILED=1
fi
docker exec mirofish-neo4j-1 neo4j-admin database start neo4j

# Config files
tar czf \"\$BACKUP_DIR/config/config_\${DATE}.tar.gz\" \\
  /opt/mirofish/.env \\
  /opt/mirofish/compose.yaml \\
  /opt/mirofish/services/caddy/Caddyfile \\
  /opt/mirofish/services/caddy/data/ \\
  /etc/docker/daemon.json \\
  /etc/iptables/rules.v4 \\
  /etc/ssh/sshd_config \\
  /etc/sysctl.d/99-hardening.conf \\
  2>/dev/null || true

# Retention: 7 days
find \"\$BACKUP_DIR/postgres\" -name \"*.sql.gz\" -mtime +7 -delete
find \"\$BACKUP_DIR/neo4j\" -name \"*.dump.gz\" -mtime +7 -delete
find \"\$BACKUP_DIR/config\" -name \"*.tar.gz\" -mtime +7 -delete

if [ \"\$FAILED\" -ne 0 ]; then
  echo \"[\$DATE] BACKUP FAILED\" >&2
  exit 1
fi

echo \"[\$DATE] BACKUP SUCCESS\"
SCRIPT"
```

- [ ] **Step 3: Make executable**

```bash
ssh dedic "sudo chmod +x /usr/local/bin/backup-dbs.sh"
```

- [ ] **Step 4: Test backup script manually**

```bash
ssh dedic "sudo /usr/local/bin/backup-dbs.sh"
```
Expected: `postgres: OK`, `neo4j: OK`, `BACKUP SUCCESS`. Neo4j will have ~60s downtime.

- [ ] **Step 5: Verify backup files exist**

Run: `ssh dedic "ls -lh /opt/mirofish/backups/postgres/ /opt/mirofish/backups/neo4j/ /opt/mirofish/backups/config/"`
Expected: `.sql.gz`, `.dump.gz`, `.tar.gz` files with non-zero size.

**Rollback:** `ssh dedic "sudo rm /usr/local/bin/backup-dbs.sh && sudo rm -rf /opt/mirofish/backups"`

---

### Task 13: Schedule cron backup (Spec 2.2)

**Files:**
- Modify: root crontab

- [ ] **Step 1: Add cron entry**

```bash
ssh dedic "echo '0 4 * * * root /usr/local/bin/backup-dbs.sh >> /var/log/backup-dbs.log 2>&1' | sudo tee /etc/cron.d/backup-dbs && sudo chmod 644 /etc/cron.d/backup-dbs"
```

- [ ] **Step 2: Verify cron entry**

Run: `ssh dedic "cat /etc/cron.d/backup-dbs"`
Expected: `0 4 * * * root /usr/local/bin/backup-dbs.sh >> /var/log/backup-dbs.log 2>&1`

**Rollback:** `ssh dedic "sudo rm /etc/cron.d/backup-dbs"`

---

### Task 14: Configure Syncthing backup sync (Spec 2.3)

**Files:**
- Syncthing config (GUI operation)

This is a GUI operation on the Syncthing web UI.

- [ ] **Step 1: Access Syncthing on server**

Open `https://sync.skatelab.ru` (or the Syncthing web UI URL from Caddy config).

- [ ] **Step 2: Add Shared Folder**

Click "Add Folder":
- Folder ID: `backups`
- Folder Path: `/opt/mirofish/backups`
- Share with: your local Syncthing device

- [ ] **Step 3: Enable staggered versioning on local machine**

On your local Syncthing: Folder Options → Versioning → Staggered:
- Max Age: 30 (days)
- Clean Interval: 3600

- [ ] **Step 4: Verify sync starts**

Check Syncthing UI — folder should show "Syncing" then "Up to Date".

**Rollback:** Remove shared folder from Syncthing UI on both sides.

---

## Wave 5: Auto-Reboot (after live-restore proven)

### Task 15: Enable unattended-upgrades auto-reboot (Spec 4.2)

**Files:**
- Modify: `/etc/apt/apt.conf.d/50unattended-upgrades`

**PREREQUISITE:** Tasks 7 (live-restore), 9 (memory limits), 11 (health checks) must be complete and verified.

- [ ] **Step 1: Verify live-restore is active**

Run: `ssh dedic "sudo docker info --format '{{.LiveRestoreEnabled}}'"`
Expected: `true`

- [ ] **Step 2: Verify health checks working**

Run: `ssh dedic "sudo docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -c healthy"`
Expected: Count > 0 (most services showing healthy)

- [ ] **Step 3: Enable auto-reboot**

```bash
ssh dedic "sudo sed -i 's|^//Unattended-Upgrade::Automatic-Reboot \"false\";|Unattended-Upgrade::Automatic-Reboot \"true\";|' /etc/apt/apt.conf.d/50unattended-upgrades"
```

- [ ] **Step 4: Set reboot time**

```bash
ssh dedic "sudo sed -i 's|^//Unattended-Upgrade::Automatic-Reboot-Time \"02:00\";|Unattended-Upgrade::Automatic-Reboot-Time \"03:00\";|' /etc/apt/apt.conf.d/50unattended-upgrades"
```

- [ ] **Step 5: Verify**

Run: `ssh dedic "grep -E 'Automatic-Reboot' /etc/apt/apt.conf.d/50unattended-upgrades | grep -v '^//'"`
Expected: Two lines showing `true` and `03:00`.

**Rollback:** Comment out both lines (replace `Unattended-Upgrade` with `//Unattended-Upgrade`), no reboot needed.

---

## Wave 6: SSH Admin User (HIGHEST RISK — do last)

### Task 16: Create admin SSH user + PermitRootLogin no (Spec 1.2)

**Files:**
- Modify: `/etc/ssh/sshd_config`
- Create: `/home/admin/` (user home)
- Create: `/etc/sudoers.d/admin`

**CRITICAL SAFETY RULES:**
1. NEVER close your root SSH session until admin login is confirmed working.
2. ALWAYS run `sshd -t` before restarting sshd.
3. Test admin login from a SEPARATE terminal.
4. Have Hetzner Robot rescue system ready as fallback.

- [ ] **Step 1: Create admin user**

```bash
ssh dedic "sudo useradd -m -s /bin/bash admin"
```

- [ ] **Step 2: Set admin password (for sudo)**

```bash
ssh dedic "sudo passwd admin"
```

**IMPORTANT:** This is interactive — you must type the password when prompted. If using a non-interactive SSH session, use: `ssh -t dedic "sudo passwd admin"`. Choose a strong password. This is used for sudo, not SSH login.

- [ ] **Step 3: Copy SSH keys**

```bash
ssh dedic "sudo mkdir -p /home/admin/.ssh && sudo cp /root/.ssh/authorized_keys /home/admin/.ssh/authorized_keys && sudo chown -R admin:admin /home/admin/.ssh && sudo chmod 700 /home/admin/.ssh && sudo chmod 600 /home/admin/.ssh/authorized_keys"
```

- [ ] **Step 4: Add sudo access**

```bash
ssh dedic "echo 'admin ALL=(ALL) ALL' | sudo tee /etc/sudoers.d/admin && sudo chmod 440 /etc/sudoers.d/admin"
```

- [ ] **Step 5: TEST ADMIN LOGIN (separate terminal!)**

Open a NEW terminal on your local machine:

```bash
ssh admin@176.9.0.156
```

Expected: Successful login. Run `sudo whoami` — should return `root` (prompts for admin password).

**DO NOT PROCEED if this fails.** Debug SSH key permissions, user config, etc. Your root session is still open.

- [ ] **Step 6: Verify admin has sudo**

```bash
ssh admin@176.9.0.156 "sudo docker ps --format 'table {{.Names}}\t{{.Status}}' | head -5"
```
Expected: Docker containers listed.

- [ ] **Step 7: Change PermitRootLogin**

```bash
ssh dedic "sudo sed -i 's/^PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config"
```

- [ ] **Step 8: Validate sshd config**

```bash
ssh dedic "sudo sshd -t && echo VALID"
```
Expected: `VALID`

- [ ] **Step 9: Restart sshd**

```bash
ssh dedic "sudo systemctl restart sshd"
```

- [ ] **Step 10: Verify admin login still works (from the other terminal)**

```bash
ssh admin@176.9.0.156 "echo ADMIN_OK"
```
Expected: `ADMIN_OK`

- [ ] **Step 11: Verify root login is denied (from a third terminal)**

```bash
ssh root@176.9.0.156
```
Expected: `Permission denied` or connection refused.

**NOW you can close the root session.**

**Rollback (Hetzner rescue):**
1. Log into Hetzner Robot (robot.hetzner.com)
2. Activate rescue system → "linux64"
3. Reboot server
4. SSH as root with rescue password
5. `mount /dev/md2 /mnt` (or correct device)
6. `chroot /mnt`
7. Edit `/etc/ssh/sshd_config`: change `PermitRootLogin no` → `PermitRootLogin prohibit-password`
8. `exit; umount /mnt; reboot`
9. Deactivate rescue in Hetzner Robot

---

## Verification Checklist

After all tasks complete, run full verification:

```bash
# 1. SSH as admin works
ssh admin@176.9.0.156 "echo SSH_ADMIN_OK"

# 2. Root SSH denied
ssh root@176.9.0.156 2>&1 | head -1  # expect permission denied

# 3. .env secure
ssh admin@176.9.0.156 "ls -la /opt/mirofish/.env"  # expect -rw------- root root

# 4. Docker healthy
ssh admin@176.9.0.156 "sudo docker ps --format 'table {{.Names}}\t{{.Status}}'"

# 5. Live-restore active
ssh admin@176.9.0.156 "sudo docker info --format '{{.LiveRestoreEnabled}}'"  # expect true

# 6. Swappiness
ssh admin@176.9.0.156 "sysctl vm.swappiness"  # expect 10

# 7. Journal limit
ssh admin@176.9.0.156 "journalctl --disk-usage"  # expect 2G max

# 8. iptables clean (no podman, no port 3000)
ssh admin@176.9.0.156 "sudo iptables -L INPUT -n --line-numbers"

# 9. Backup works
ssh admin@176.9.0.156 "sudo /usr/local/bin/backup-dbs.sh && ls -lh /opt/mirofish/backups/*/"

# 10. Cron scheduled
ssh admin@176.9.0.156 "cat /etc/cron.d/backup-dbs"

# 11. AppArmor active
ssh admin@176.9.0.156 "sudo aa-status --enabled"
```
