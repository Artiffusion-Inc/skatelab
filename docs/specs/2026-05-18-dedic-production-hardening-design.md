# Dedic Production Hardening Spec

**Goal:** Харденинг прод-сервера 176.9.0.156 (skatelab.ru) по enterprise best practices. 16 пунктов аудита → 4 зоны.

**Server:** Hetzner, Debian Trixie 13.5, kernel 6.12.73, 62GB RAM, 905GB disk, Docker CE 29.5.1

---

## Zone 1: Secrets & Access

### 1.1 .env file permissions

`.env` содержит API-ключи, пароли БД. Сейчас `644` (world-readable), owner `mirofish:mirofish`.

**Fix:** `chmod 600 /opt/mirofish/.env && chown root:root /opt/mirofish/.env`

Docker compose работает от root — читает .env без проблем.

### 1.2 SSH user: admin

Создать отдельного пользователя для SSH вместо root.

- `useradd -m -s /bin/bash admin`
- Добавить SSH-ключи из `/root/.ssh/authorized_keys` в `/home/admin/.ssh/authorized_keys`
- sudo: `admin ALL=(ALL) ALL` с паролем (не NOPASSWD)
- sshd_config: `PermitRootLogin no`
- Проверить вход по ключу до закрытия SSH-сессии

### 1.3 Remove dead sudoers

`/etc/sudoers.d/mirofish-podman` содержит `mirofish ALL=(ALL) NOPASSWD: /usr/bin/podman` — podman удалён.

**Fix:** `rm /etc/sudoers.d/mirofish-podman`

### 1.4 X11Forwarding

sshd_config: `X11Forwarding yes` → `X11Forwarding no`. Headless сервер не нуждается в X11.

### 1.5 Docker group

`docker` group = root equivalent. НЕ добавлять mirofish-user. Все docker команды через sudo от admin.

### 1.6 Lock mirofish user

`mirofish` user существует, но podman удалён. User не нужен для работы (docker compose работает от root).

**Fix:** `usermod -L mirofish && usermod -s /usr/sbin/nologin mirofish`

Не удалять полностью — UID может владеть файлами.

### 1.7 Valkey persistent mount

Valkey (Redis) работает без persistent volume — data loss при container recreate.

**Fix:** Добавить в compose.yaml:
```yaml
valkey:
  volumes:
    - ./services/valkey/data:/data
```

Создать: `mkdir -p /opt/mirofish/services/valkey/data`

---

## Zone 2: Backups

### 2.1 Backup script

`/usr/local/bin/backup-dbs.sh`:

```bash
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/opt/mirofish/backups"
DATE=$(date +%Y-%m-%d_%H%M)
FAILED=0

mkdir -p "$BACKUP_DIR/postgres" "$BACKUP_DIR/neo4j" "$BACKUP_DIR/config"

# Postgres (hot backup, no downtime)
if docker exec mirofish-postgres-1 pg_dumpall -U postgres | \
  gzip > "$BACKUP_DIR/postgres/pg_dumpall_${DATE}.sql.gz"; then
  gunzip -t "$BACKUP_DIR/postgres/pg_dumpall_${DATE}.sql.gz"
else
  FAILED=1
fi

# Neo4j (requires stop → dump → start, ~60s downtime)
docker exec mirofish-neo4j-1 neo4j-admin database stop neo4j
docker exec mirofish-neo4j-1 neo4j-admin database dump neo4j \
  --to-stdout | gzip > "$BACKUP_DIR/neo4j/neo4j_${DATE}.dump.gz" || FAILED=1
docker exec mirofish-neo4j-1 neo4j-admin database start neo4j

if [ "$FAILED" -eq 0 ]; then
  gunzip -t "$BACKUP_DIR/neo4j/neo4j_${DATE}.dump.gz"
fi

# Config files
tar czf "$BACKUP_DIR/config/config_${DATE}.tar.gz" \
  /opt/mirofish/.env \
  /opt/mirofish/compose.yaml \
  /opt/mirofish/services/caddy/Caddyfile \
  /opt/mirofish/services/caddy/data/ \
  /etc/docker/daemon.json \
  /etc/iptables/rules.v4 \
  /etc/ssh/sshd_config \
  /etc/sysctl.d/99-hardening.conf \
  2>/dev/null || true  # some files may not exist yet on first run

# Retention: 7 days
find "$BACKUP_DIR/postgres" -name "*.sql.gz" -mtime +7 -delete
find "$BACKUP_DIR/neo4j" -name "*.dump.gz" -mtime +7 -delete
find "$BACKUP_DIR/config" -name "*.tar.gz" -mtime +7 -delete

if [ "$FAILED" -ne 0 ]; then
  echo "BACKUP FAILED at $(date)" >&2
  exit 1
fi
```

Создать директории: `mkdir -p /opt/mirofish/backups/{postgres,neo4j,config}`

### 2.2 Cron schedule

`04:00 daily` — после unattended-upgrades (reboot в 03:00) + время на recovery всех сервисов.

```
0 4 * * * /usr/local/bin/backup-dbs.sh >> /var/log/backup-dbs.log 2>&1
```

### 2.3 Syncthing sync

Syncthing уже работает на сервере. Добавить `/opt/mirofish/backups` как Shared Folder → локальная машина.

Retention: 7 дней на сервере. На локальной машине — Syncthing с staggered versioning (настроить в GUI: Folder Options → Versioning → Staggered, keep 30 days).

**Важно:** `.env` содержит secrets. НЕ синхронизировать через Syncthing в открытом виде. Config backup (2.1) уже включает `.env` в зашифрованном tar.

---

## Zone 3: Docker Hardening

### 3.1 daemon.json

Создать `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  },
  "live-restore": true
}
```

- `max-size: 50m, max-file: 5` — макс 250MB логов на контейнер. Без этого json-file драйвер растёт бесконечно. 30MB (10m x 3) слишком мало — cadvisor генерит ~8MB/день.
- `live-restore: true` — контейнеры переживают daemon restart. Критично для прод (apt upgrade docker → без downtime).

Применение: `systemctl restart docker`. **Важно:** первый restart с live-restore ещё НЕ переживут контейнеры — live-restore начинает работать только ПОСЛЕ того как daemon запустится с ним. Поэтому: создать daemon.json → restart docker (контейнеры упадут, но поднимутся с `unless-stopped`) → live-restore активен для последующих restart'ов.

### 3.2 iptables: remove port 3000 (combine with 3.3)

См. задачу 3.3 — все iptables изменения делаются одной атомарной операцией.

Правило `tcp dpt:3000` открывает MiroFish мимо Caddy (прямой HTTP без TLS).

**Fix:** (в рамках 3.3):
```bash
iptables -D INPUT -p tcp --dport 3000 -j ACCEPT
```

Правило 9 (`tcp dpt:3000`) открывает MiroFish мимо Caddy (прямой HTTP без TLS).

**Fix:** `iptables -D INPUT -p tcp --dport 3000 -j ACCEPT`

Сохранить: `iptables-save > /etc/iptables/rules.v4`

### 3.3 iptables: delete podman subnet rules + wildcard ACCEPT

Правила 1-2 (`10.89.0.0/24`) — podman subnet, podman удалён.
Правило 3 — `ACCEPT all` без ограничений source/dest — делает весь firewall бессмысленным.

Docker обрабатывает bridge-трафик через FORWARD/DOCKER цепочки, INPUT правила для Docker subnet НЕ нужны.

**Fix:** Удалить правила 1-3 (podman + wildcard):

```bash
# Backup current rules
iptables-save > /etc/iptables/rules.v4.bak

# Delete by specification (not line number — avoids shifting)
iptables -D INPUT -s 10.89.0.0/24 -j ACCEPT
iptables -D INPUT -d 10.89.0.0/24 -j ACCEPT
# Verify rule 3 is NOT loopback-only before deleting:
iptables -L INPUT -v -n --line-numbers | head -5
# If rule 3 has no -i lo, delete it:
iptables -D INPUT 3  # wildcard ACCEPT — if no interface restriction

iptables-save > /etc/iptables/rules.v4
```

### 3.4 AppArmor

Docker автоматически применяет профиль `docker-default` если AppArmor установлен.

**Fix:** `apt install apparmor apparmor-profiles`

Перезапуск контейнеров не нужен — профиль применяется при следующем `docker compose up`.

---

## Zone 4: System Hardening

### 4.1 Swappiness

Сейчас `60` (дефолт). При 62GB RAM — ядро свопает слишком рано.

**Важно:** Сначала добавить memory limits для ВСЕХ контейнеров (16/19 без limits). Без limits swappiness=10 → OOM kill при memory pressure.

**Fix (Phase 1):** Добавить memory limits в compose.yaml для всех сервисов:

```yaml
# Примеры (плюс существующие windmill_worker: 1536M, 9router: 1G, cadvisor: 256M)
postgres: 2g
neo4j: 4g
mirofish: 4g
windmill_server: 2g
searxng: 1g
valkey: 512m
miniflux: 512m
rsshub: 512m
caddy: 256m
ntfy: 256m
syncthing: 512m
qbittorrent: 512m
baikal: 256m
mosquitto: 128m
tor: 128m
```

**Fix (Phase 2):** `echo 10 > /proc/sys/vm/swappiness`

Persist: `/etc/sysctl.d/99-hardening.conf`:
```
vm.swappiness=10
```

### 4.2 Unattended-upgrades: auto-reboot

Секурити патчи ядра требуют перезагрузки. Сейчас reboot disabled — патчи не применяются.

**Важно:** Сначала добавить health checks + depends_on для критических сервисов. Без этого mirofish crash-loop после reboot (depends on slow neo4j startup 30-60s).

**Fix:** Добавить health checks в compose.yaml где отсутствуют. Затем:

`/etc/apt/apt.conf.d/50unattended-upgrades`:
```
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:00";
```

Reboot в 03:00, backup в 04:00 (не 03:30 — дать время на recovery).

### 4.3 Journal size

Сейчас 483MB без лимита (~12MB/hour). 500MB = ~42 часа — критически мало для прод.

**Fix:** `/etc/systemd/journald.conf`:
```
SystemMaxUse=2G
```

2G = ~7 дней retention. `systemctl restart systemd-journald`

### 4.4 Caddy TLS

HTTP challenge работает корректно (Let's Encrypt через Cloudflare DNS-only mode). DNS challenge — overkill для текущего кейса. Оставить как есть.

---

## Implementation Order

1. 1.1 (.env permissions) — zero risk, immediate
2. 1.3 (remove dead sudoers — filename: `/etc/sudoers.d/mirofish-podman`)
3. 1.4 (X11Forwarding no)
4. 1.5 (docker group policy)
5. 1.6 (lock mirofish user)
6. 1.7 (Valkey persistent mount)
7. 3.2 + 3.3 (iptables cleanup — atomic, backup rules.v4 first)
8. 3.1 (daemon.json — accept first-restart downtime, then live-restore active)
9. 3.4 (AppArmor — may defer, containers need recreate to apply)
10. 4.1 Phase 1 (memory limits in compose.yaml) → Phase 2 (swappiness 10)
11. 4.3 (journal 2G)
12. 2.1 (backup script — with Neo4j stop/dump/start)
13. 2.2 (cron at 04:00)
14. 2.3 (Syncthing with staggered versioning)
15. 4.2 (auto-reboot — only after live-restore proven)
16. 1.2 (admin user + PermitRootLogin no — highest risk, do LAST when stable)

1.2 сознательно последняя — `PermitRootLogin prohibit-password` уже блокирует парольный root вход. Прирост безопасности от `no` минимальный vs риск lockout.

## Risks

| Риск | Митигация |
|---|---|
| `PermitRootLogin no` → потеря доступа | Проверить SSH вход для admin ДО закрытия root сессии. Hetzner rescue как fallback |
| `systemctl restart docker` → downtime контейнеров | Первый restart с live-restore всё равно уронит контейнеры (они поднимутся с `unless-stopped`). Последующие restart'ы безопасны |
| iptables замена → временный дроп трафика | `iptables-save` backup перед изменениями. Использовать `-D` с полной спецификацией, не номера строк |
| Neo4j dump на running DB → silent failure | Stop/dump/start. Не использовать pipe с `set -e` — раздельные скрипты |
| daemon.json syntax error → dockerd не стартует | `python3 -m json.tool` перед restart. SSH независим от Docker |
| Swappiness 10 без memory limits → OOM | Добавить limits в compose.yaml ПЕРЕД изменением swappiness |
| Auto-reboot + незрелые health checks → crash loops | Health checks + depends_on ПЕРЕД включением auto-reboot |
| AppArmor docker-default → container fail | Профиль применяется только при `docker compose up`. Проверить `dmesg` после |
