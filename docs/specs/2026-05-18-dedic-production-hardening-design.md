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

`/etc/sudoers.d/mirofish` содержит `mirofish ALL=(ALL) NOPASSWD: /usr/bin/podman` — podman удалён.

**Fix:** `rm /etc/sudoers.d/mirofish`

### 1.4 X11Forwarding

sshd_config: `X11Forwarding yes` → `X11Forwarding no`. Headless сервер не нуждается в X11.

### 1.5 Docker group

`docker` group = root equivalent. НЕ добавлять mirofish-user. Все docker команды через sudo от admin.

---

## Zone 2: Backups

### 2.1 Backup script

`/usr/local/bin/backup-dbs.sh`:

```bash
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/opt/mirofish/backups"
DATE=$(date +%Y-%m-%d_%H%M)

# Postgres
docker exec mirofish-postgres-1 pg_dumpall -U postgres | \
  gzip > "$BACKUP_DIR/postgres/pg_dumpall_${DATE}.sql.gz"

# Neo4j
docker exec mirofish-neo4j-1 neo4j-admin database dump neo4j \
  --to-stdout | gzip > "$BACKUP_DIR/neo4j/neo4j_${DATE}.dump.gz"

# Retention: 7 days
find "$BACKUP_DIR/postgres" -name "*.sql.gz" -mtime +7 -delete
find "$BACKUP_DIR/neo4j" -name "*.dump.gz" -mtime +7 -delete
```

Создать директории: `mkdir -p /opt/mirofish/backups/{postgres,neo4j}`

### 2.2 Cron schedule

`03:30 daily` — после unattended-upgrades (которые могут перезагрузить в 03:00).

```
30 3 * * * /usr/local/bin/backup-dbs.sh >> /var/log/backup-dbs.log 2>&1
```

### 2.3 Syncthing sync

Syncthing уже работает на сервере. Добавить `/opt/mirofish/backups` как Shared Folder → локальная машина.

Retention: 7 дней на сервере. На локальной машине — сколько нужно (Syncthing сохраняет все полученные файлы).

---

## Zone 3: Docker Hardening

### 3.1 daemon.json

Создать `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true
}
```

- `max-size: 10m, max-file: 3` — макс 30MB логов на контейнер. Без этого json-file драйвер растёт бесконечно.
- `live-restore: true` — контейнеры переживают daemon restart. Критично для прод (apt upgrade docker → без downtime).

Применение: `systemctl restart docker`. С `live-restore` контейнеры не упадут.

### 3.2 iptables: remove port 3000

Правило 9 (`tcp dpt:3000`) открывает MiroFish мимо Caddy (прямой HTTP без TLS).

**Fix:** `iptables -D INPUT -p tcp --dport 3000 -j ACCEPT`

Сохранить: `iptables-save > /etc/iptables/rules.v4`

### 3.3 iptables: podman subnet → docker subnet

Правила 1-2 (`10.89.0.0/24`) — podman subnet. Docker использует `172.16.0.0/12`.

**Fix:** Заменить `10.89.0.0/24` на `172.16.0.0/12` в правилах INPUT.

```bash
iptables -R INPUT 1 -s 172.16.0.0/12 -j ACCEPT
iptables -R INPUT 2 -d 172.16.0.0/12 -j ACCEPT
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

**Fix:** `echo 10 > /proc/sys/vm/swappiness`

Persist: `/etc/sysctl.d/99-hardening.conf`:
```
vm.swappiness=10
```

### 4.2 Unattended-upgrades: auto-reboot

Секурити патчи ядра требуют перезагрузки. Сейчас reboot disabled — патчи не применяются.

**Fix:** `/etc/apt/apt.conf.d/50unattended-upgrades`:
```
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:00";
```

Reboot в 03:00, backup в 03:30 — безопасная последовательность.

### 4.3 Journal size

Сейчас 483MB без лимита.

**Fix:** `/etc/systemd/journald.conf`:
```
SystemMaxUse=500M
```

`systemctl restart systemd-journald`

### 4.4 Caddy TLS

HTTP challenge работает корректно (Let's Encrypt через Cloudflare DNS-only mode). DNS challenge — overkill для текущего кейса. Оставить как есть.

---

## Implementation Order

1. Zone 1 (Secrets & Access) — самый высокий риск, быстрый фикс
2. Zone 3 (Docker Hardening) — daemon.json, iptables cleanup
3. Zone 2 (Backups) — скрипт + cron + syncthing
4. Zone 4 (System Hardening) — sysctl, journald, autoreboot

Zones 1 и 3 можно делать параллельно (независимые).

## Risks

| Риск | Митигация |
|---|---|
| `PermitRootLogin no` → потеря доступа | Проверить SSH вход для admin ДО закрытия root сессии |
| `systemctl restart docker` → downtime контейнеров | `live-restore: true` применить ДО restart |
| iptables замена subnet → временный дроп трафика | Быстрая замена (`-R` вместо `-D`+`-I`) |
