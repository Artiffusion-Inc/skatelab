# Dedic Production Hardening — Multi-Agent Review Report

**Date:** 2026-05-18
**Spec:** `docs/specs/2026-05-18-dedic-production-hardening-design.md`
**Reviewers:** 5 specialized agents (Security, Backup, SRE/Ops, Parallelization, Risk)

---

## Executive Summary

Spec покрывает реальные проблемы, но содержит **4 критических ошибки** и **8 значимых упущений**. Без исправлений реализация спека приведёт к сломанному бэкапу, ослаблению firewall и потенциальному OOM. Наиболее опасные находки:

1. Neo4j backup на running DB → скрипт падает, postgres бэкап не создаётся
2. iptables INPUT rule 3 = wildcard ACCEPT — firewall фактически открыт
3. `172.16.0.0/12` — слишком широкая subnet, ослабляет firewall
4. Swappiness 10 без memory limits на 16/19 контейнеров → OOM kill risk

---

## Critical Findings (Must Fix Before Implementation)

### C1. Neo4j Backup Script Will Fail

**Spec (2.1):** `neo4j-admin database dump neo4j --to-stdout` на running database.

**Reality:** Neo4j Community Edition `neo4j-admin database dump` requires stopped database. On a running DB, command exits with error. With `set -e` in script, **entire backup aborts** — postgres backup also lost.

**Fix:** Two options:
1. **Stop/dump/start** (downtime ~60s):
   ```bash
   docker exec mirofish-neo4j-1 neo4j-admin database stop neo4j
   docker exec mirofish-neo4j-1 neo4j-admin database dump neo4j --to-stdout | gzip > "$BACKUP_DIR/neo4j/neo4j_${DATE}.dump.gz"
   docker exec mirofish-neo4j-1 neo4j-admin database start neo4j
   ```
2. **Separate scripts** — postgres and neo4j in independent scripts, so one failure doesn't kill the other.

### C2. INPUT Chain Rule 3 — Verify Before Deleting

**Current iptables** (verified on server):
```
Chain INPUT (policy DROP)
1  ACCEPT  all  --  10.89.0.0/24  0.0.0.0/0
2  ACCEPT  all  --  0.0.0.0/0  10.89.0.0/24
3  ACCEPT  all  --  0.0.0.0/0  0.0.0.0/0
4  ACCEPT  all  --  0.0.0.0/0  0.0.0.0/0  ctstate RELATED,ESTABLISHED
...
```

Rule 3 shows `ACCEPT all` without visible interface. **Must verify with `iptables -L INPUT -v -n --line-numbers`** — if it's `-i lo` (loopback), it's safe. If it's truly wildcard (no interface restriction), it nullifies the entire firewall.

**Action:** Run `iptables -L INPUT -v -n --line-numbers` to check. If wildcard → delete. If loopback → keep.

### C3. iptables Subnet Too Broad

**Spec (3.3):** Replace `10.89.0.0/24` with `172.16.0.0/12`.

**Problem:** `172.16.0.0/12` = 172.16.0.0–172.31.255.255 (1M+ addresses). Actual Docker network = `172.18.0.0/16`. Whitelisting `/12` exposes all Docker traffic and any future networks in that range.

**Better approach:** Docker handles bridge traffic via FORWARD/DOCKER chains, not INPUT. Rules 1-2 (podman subnet) are **unnecessary** for Docker. Delete them entirely:
```bash
iptables -D INPUT -s 10.89.0.0/24 -j ACCEPT
iptables -D INPUT -d 10.89.0.0/24 -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```

### C4. Swappiness 10 Without Memory Limits

**Spec (4.1):** `vm.swappiness=10`

**Problem:** 16 of 19 containers have NO memory limits. With swappiness=10, kernel avoids swap until extreme memory pressure → sudden OOM kills. A runaway container (neo4j large query, mirofish image processing) could trigger system-wide OOM, killing SSH or dockerd.

**Fix:** Set memory limits FIRST, then lower swappiness:
- Phase 1: Add `deploy.resources.limits.memory` to all containers in compose.yaml
- Phase 2: Lower swappiness to 30 (conservative), then 10 after monitoring

---

## Significant Findings (Should Fix)

### S1. Missing Backups for Critical Files

Spec only backs up postgres and neo4j. Missing:
- `/opt/mirofish/.env` (API keys, DB passwords)
- `/opt/mirofish/compose.yaml`
- `/opt/mirofish/services/caddy/Caddyfile`
- `/opt/mirofish/services/caddy/data/` (TLS certs)
- Valkey data (no persistent mount at all — data loss on restart)

**Fix:** Add config backup section to script:
```bash
# Config backup
tar czf "$BACKUP_DIR/config/config_${DATE}.tar.gz" \
  /opt/mirofish/.env \
  /opt/mirofish/compose.yaml \
  /opt/mirofish/services/caddy/Caddyfile \
  /opt/mirofish/services/caddy/data/ \
  /etc/docker/daemon.json \
  /etc/iptables/rules.v4 \
  /etc/ssh/sshd_config
```

Add Valkey persistent mount to compose.yaml:
```yaml
valkey:
  volumes:
    - ./services/valkey/data:/data
```

### S2. No Backup Encryption

Backups synced via Syncthing contain DB passwords, API keys (in postgres dumps). No encryption.

**Fix:** Use `age` encryption before Syncthing sync:
```bash
tar czf - ... | age -r "$RECIPIENT_PUBKEY" > "$BACKUP_DIR/config/config_${DATE}.tar.gz.age"
```

### S3. No Backup Verification

No integrity check, no restore testing. Silent failure → false confidence.

**Fix:**
- Add `gunzip -t` / `pg_restore --list` verification after backup
- Monthly restore test to separate location
- ntfy alert on backup failure

### S4. Journal 500MB Too Small

Current journal: 483MB in ~40 hours (~12MB/hour). 500MB = ~42 hours retention. Weekend incident = no logs by Monday.

**Fix:** Increase to 2-4GB for 1-2 weeks retention:
```
SystemMaxUse=2G
```

### S5. Log Rotation Too Restrictive

Spec: `max-size: 10m, max-file: 3` = 30MB per container. cadvisor alone generates ~7.9MB/day. 30MB = ~4 days.

**Fix:**
- Default: `max-size: 50m, max-file: 5` (250MB per container)
- Per-container overrides for high-volume services in compose.yaml

### S6. Auto-Reboot Without Dependency Orchestration

Docker `unless-stopped` restarts all containers simultaneously. mirofish depends on neo4j (slow startup 30-60s) → crash loop until neo4j ready. Backup at 03:30 may run against partially recovered services.

**Fix:**
- Ensure all critical services have health checks in compose.yaml
- Add `depends_on` with `condition: service_healthy` where missing
- Move backup to 04:00 with pre-check script verifying all containers healthy
- Add post-reboot validation script

### S7. mirofish User Still Active

`mirofish` system user exists but podman removed. Dead sudoers entry (1.3) is being removed, but user account remains.

**Fix:** `usermod -L mirofish && usermod -s /usr/sbin/nologin mirofish` (lock + disable shell)

### S8. No Container Security Hardening

Spec misses Docker-level security:
- No `cap_drop: ALL` + minimal `cap_add` per service
- No `security_opt: no-new-privileges:true`
- No network segmentation (all 19 services on flat `app_network`)

**Recommendation (future iteration):**
- Separate networks: `db_network` (postgres, neo4j, valkey), `app_network` (caddy, mirofish, windmill), `selfhost_network` (miniflux, etc.)
- Add `cap_drop: ALL` to searxng, ntfy, baikal (already has some)

---

## Parallelization Analysis (from Agent 4)

### Dependency Graph

```
Wave 1 (leaf nodes — no dependencies):
  1.1 .env permissions
  1.3 Remove dead sudoers
  1.4 X11Forwarding no
  1.5 Docker group policy
  3.2 Remove port 3000 iptables
  3.4 Install AppArmor
  4.1 Swappiness (but see C4 — needs memory limits first)
  4.3 Journal size

Wave 2 (depends on Wave 1):
  1.2 Create admin SSH user (needs .env secured first for safety)
  3.1 daemon.json + live-restore (needs iptables cleanup first for safety)
  3.3 Replace podman subnet iptables (after port 3000 removal, rule numbers shift)
  4.2 Auto-reboot (needs health checks configured first — see S6)

Wave 3 (depends on Wave 2):
  2.1 Backup script (needs admin user for cron, needs fixed iptables)
  2.2 Cron schedule (needs backup script)

Wave 4 (depends on Wave 3):
  2.3 Syncthing sync (needs backup files to exist)
```

### Critical Path

`1.1 → 1.2 → 2.1 → 2.2 → 2.3` = 5 steps sequential (SSH safety → backup chain)

### SSH Safety Bottleneck

Task 1.2 (admin user + PermitRootLogin no) is highest-risk. Must:
1. Create admin user
2. Copy SSH keys
3. Test admin login from NEW session
4. Only then: `PermitRootLogin no`
5. Keep root session open until admin verified

### iptables Batching

Tasks 3.2 and 3.3 both modify iptables. Combine into single atomic operation:
```bash
iptables-save > /etc/iptables/rules.v4.bak
# Delete rule 3 (wildcard ACCEPT) if confirmed
iptables -D INPUT 3
# Delete podman rules
iptables -D INPUT -s 10.89.0.0/24 -j ACCEPT
iptables -D INPUT -d 10.89.0.0/24 -j ACCEPT
# Delete port 3000
iptables -D INPUT -p tcp --dport 3000 -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```

Use `-D` with full rule specification (not line numbers) to avoid number shifting issues.

---

## Risk Assessment (from Agent 5)

### Highest Risk Items

| Task | Risk | Impact | Probability | Recovery |
|------|------|--------|-------------|----------|
| 1.2 PermitRootLogin no | SSH lockout | Complete server loss | Medium | Hetzner rescue → edit sshd_config |
| 3.1 daemon.json + restart | dockerd won't start | All services down | Low | Hetzner rescue → remove daemon.json |
| 3.2-3.3 iptables changes | Drop SSH traffic | Complete server loss | Low | Hetzner rescue → iptables-restore |
| 2.1 Neo4j backup | Data inconsistency | Silent backup failure | High | Fix script (see C1) |
| 4.1 Swappiness 10 | OOM kills | Random process death | Medium | `echo 60 > /proc/sys/vm/swappiness` |

### SSH Lockout Prevention Checklist

- [ ] Create admin user with home + shell
- [ ] Copy `/root/.ssh/authorized_keys` → `/home/admin/.ssh/authorized_keys`
- [ ] `chmod 700 /home/admin/.ssh && chmod 600 /home/admin/.ssh/authorized_keys`
- [ ] `chown -R admin:admin /home/admin/.ssh`
- [ ] Add `admin ALL=(ALL) ALL` to sudoers
- [ ] **Test SSH login as admin from NEW terminal** (keep root session open)
- [ ] `sshd -t` to validate config
- [ ] `PermitRootLogin no`
- [ ] `systemctl restart sshd`
- [ ] **Verify admin still works after restart**

---

## Recommended Spec Updates

1. **C1:** Fix Neo4j backup (stop/dump/start or separate scripts)
2. **C2:** Investigate and delete iptables rule 3 (wildcard ACCEPT)
3. **C3:** Delete podman subnet rules entirely (don't replace with /12)
4. **C4:** Add memory limits to compose.yaml before lowering swappiness
5. **S1:** Add config backup section
6. **S2:** Add `age` encryption for backups
7. **S3:** Add backup verification + restore testing
8. **S4:** Increase journal to 2G
9. **S5:** Increase log rotation defaults (50m x 5)
10. **S6:** Add health checks + dependency orchestration before auto-reboot
11. **S7:** Lock mirofish user
12. **S8:** Add cap_drop/network segmentation as future iteration

---

## Additional Findings

- **Valkey no persistent mount** — data lost on container recreate. Add volume.
- **mirofish container unhealthy** — fix before hardening, not after
- **No monitoring/alerting** — ntfy exists but not wired to container health
- **No container update strategy** — no watchtower, no CVE scanning
- **docker group = root equivalent** — spec correctly avoids adding users to docker group, but doesn't mention that windmill_worker already has `/var/run/docker.sock:ro` mounted (effectively root access via API)
- **Spec bug: sudoers filename** — actual file is `/etc/sudoers.d/mirofish-podman`, not `/etc/sudoers.d/mirofish`. `rm` on wrong name silently succeeds, dead rule remains.
- **Live-restore first-restart gap** — containers WILL stop on first daemon.json restart. Only subsequent restarts are safe.
- **1.2 should be LAST task** — `PermitRootLogin prohibit-password` already blocks password auth. `no` adds minimal incremental security vs significant lockout risk. Do when everything else is stable.

## Revised Execution Order (from Risk Agent)

1. 1.1 (.env permissions) — zero risk
2. 1.3 (remove dead sudoers — correct filename!)
3. 1.4 (X11Forwarding no)
4. 1.5 (docker group policy — verify no one is in docker group)
5. 1.6 (lock mirofish user)
6. 1.7 (Valkey persistent mount)
7. 3.2 + 3.3 (iptables cleanup — atomic, save backup first)
8. 3.1 (daemon.json — accept first-restart downtime)
9. 3.4 (AppArmor — defer if concerned about latent breakage)
10. 4.1 (swappiness — after memory limits)
11. 4.3 (journal 2G)
12. 2.1 (backup script — with Neo4j fix)
13. 2.2 (cron at 04:00)
14. 2.3 (Syncthing with staggered versioning)
15. 4.2 (auto-reboot — LAST before SSH, only after live-restore proven)
16. 1.2 (admin user + PermitRootLogin no — highest risk, do when stable)
