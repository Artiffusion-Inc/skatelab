# Android CI & Development Optimization — Agent Review Report

> 5 специализированных агентов проанализировали спеку `2026-05-21-android-ci-optimization-design.md`. Ниже — синтез находок с приоритизацией.

---

## Критические исправления к спеке

### 1. Заменить `actions/cache` на `gradle/actions/setup-gradle@v4`

**Кто обнаружил:** CI/CD эксперт

Текущий composite action использует `actions/cache@v4` для `~/.gradle/caches`. Gradle team **явно предупреждает** — это конфликтует с `setup-gradle`, не сохраняет configuration cache, и не умеет чистить устаревшие записи. `setup-gradle` кэширует: dependency jars, build-cache, configuration-cache (зашифрованный), generated-gradle-jars — с fine-grained ключами и автоочисткой.

**Изменение:** В `.github/actions/setup-android/action.yml` заменить `actions/cache` на `gradle/actions/setup-gradle@v4` с `cache-encryption-key`. Создать секрет `GRADLE_CACHE_ENCRYPTION_KEY`.

**Реальный кейс:** 13 мин → 5.5 мин билд после включения encrypted configuration cache.

### 2. noVNC без авторизации = критическая уязвимость

**Кто обнаружил:** Security эксперт

Спека указывает `http://176.9.0.156:6080` как способ доступа. noVNC **не имеет встроенной авторизации**. VNC password ограничен 8 символами (DES-based), подвержен CVE-2025-27458.

**Изменение:**
- Убрать `http://176.9.0.156:6080` из спеки
- Доступ только через: (а) SSH туннель `ssh -L 6080:127.0.0.1:6080 -p 43210 dev@176.9.0.156`, или (б) Caddy route `emu.skatelab.ru` с Cloudflare Access / `basic_auth`
- Порт 6080 привязан к `127.0.0.1` — спека уже это делает, но текст противоречит

### 3. ADB порт 5555 не публиковать

**Кто обнаружили:** Security + Docker эксперты

ADB на порту 5555 = root shell на эмуляторе. На эмуляторных образах `adb root` работает напрямую.

**Изменение:** В compose НЕ публиковать порт 5555. ADB только через `docker exec android-emulator adb install /apk/app.apk`.

### 4. `group_add: "kvm"` обязателен

**Кто обнаружил:** Docker эксперт

Без `group_add` контейнер не получит доступ к `/dev/kvm` при запуске от non-root пользователя. Известная проблема (budtmo/docker-android#369).

**Изменение:** Добавить в compose:
```yaml
group_add:
  - "kvm"  # GID = getent group kvm на хосте
```

### 5. `fetch-depth: 0` вместо `fetch-depth: 1` для build jobs

**Кто обнаружил:** CI/CD эксперт

`git rev-list --count HEAD` и `git describe` (APK versioning из спеки) требуют полную историю. Shallow clone даёт неверный `versionCode`. Также configuration cache лучше работает с полной историей.

**Изменение:** В `build-debug` и `build-release` — `fetch-depth: 0`. В `lint` и `test` — `fetch-depth: 1` (история не нужна).

---

## Высокоэффективные оптимизации

### 6. KAPT → KSP миграция

**Кто обнаружил:** Gradle эксперт

Hilt 2.56.1 официально поддерживает KSP (с версии 2.48). В проекте только один KAPT processor — Hilt compiler. Миграция = 3 файла, низкий риск.

**Влияние:** 15-25% быстрее инкрементальные сборки. Убирает KAPT как blocker для configuration cache.

**Шаги:**
- `build.gradle.kts`: `kapt` → `ksp` plugin
- `app/build.gradle.kts`: `kapt(...)` → `ksp(...)`
- `gradle.properties`: `ksp.project.isolation.enabled=true`

### 7. Прегенерация Protobuf источников

**Кто обнаружил:** Gradle эксперт

`imu.proto` — 3 сообщения, 33 строки. Меняется крайне редко. Protobuf plugin 0.9.5 — hard blocker для configuration cache (issue #687, нет фикса).

**Влияние:** Убирает второй из трёх config-cache blockers. Убирает `protoc` binary download.

**Шаги:** Один раз сгенерировать Java Lite sources, закоммитить в `app/src/main/java/.../proto/`, убрать plugin из build.gradle.kts.

### 8. JVM heap tuning: 2GB → 4GB

**Кто обнаружили:** Gradle + CI/CD эксперты (сошлись независимо)

Текущий `-Xmx2g` вызывает частые GC pauses. NowInAndroid (аналогичный проект) использует `-Xmx4g -Xms4g`. Рекомендация с доказательной базой от Jason Pearson — НЕ ставить `MaxMetaspaceSize` на JDK 17+.

**Ключевые параметры:**
```properties
org.gradle.jvmargs=-Xmx4g -Xms4g -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=256m -XX:+HeapDumpOnOutOfMemoryError
kotlin.daemon.jvmargs=-Xmx4g -Xms4g -XX:+UseG1GC -XX:ReservedCodeCacheSize=320m
```

### 9. Blacksmith runners вместо ubuntu-latest

**Кто обнаружил:** CI/CD эксперт

Уже платится за Blacksmith. Android — последний workflow на стандартных runner'ах. 30-50% быстрее.

**Распределение:** `lint`/`test` → 2vcpu, `build-debug`/`build-release` → 4vcpu (Hilt kapt + R8 CPU-intensive).

### 10. Skip build-release на PR

**Кто обнаружил:** CI/CD эксперт

`assembleRelease` с R8/ProGuard = 2-3x дольше debug. Для PR достаточно debug APK.

**Условие:** `if: github.event_name == 'push' && github.ref == 'refs/heads/master'`

---

## Улучшения DX (Developer Experience)

### 11. Quick wins — без инфраструктурных изменений

| Что | Команда | Экономия |
|-----|---------|----------|
| `ghapk` alias | `gh run download ... -n apk-debug && adb install` | 30s → 5s на скачивание |
| SSH build aliases | `ssh dedic "./gradlew assembleDebug" && scp apk && adb install` | 0 локальной RAM |
| `scrcpy` | `pacman -S scrcpy` | 20ms latency зеркалирование телефона |
| Standalone `ktlint` | Скачивание binary | 200MB вместо 5GB (нет Gradle daemon) |
| `gh run watch` | Уже установлен | Терминал блокируется до завершения CI |
| ADB over SSH tunnel | `ssh -R 5037:localhost:5037 dedic` | Build на dedic → install на телефон без промежуточного копирования |

### 12. Syncthing для синхронизации кода

**Кто обнаружил:** DX эксперт

Syncthing уже работает на dedic (`infra-syncthing-1`). Настроить bidirectional sync `mobile/` — код синхронизируется за 5-15 сек без `git pull`.

### 13. Pre-push hook — ktlintCheck на dedic

**Кто обнаружил:** DX эксперт

Git pre-push hook SSH'ется на dedic, запускает `ktlintCheck`, блокирует push при ошибке. 0 локальной RAM.

### 14. ntfy уведомления

**Кто обнаружил:** DX эксперт

ntfy уже работает на dedic (`infra-ntfy-1`). Добавить webhook step в workflow → push-уведомление на телефон когда CI завершён.

### 15. Compose Live Edit — НЕ доступен без Android Studio

**Кто обнаружил:** DX эксперт (исследование)

Google привязал Live Edit к Android Studio. Нет CLI эквивалента, нет Gradle task, нет способа запустить из Neovim/VS Code. Это фундаментальное ограничение CLI-разработки на Android.

---

## Безопасность — дополнительные рекомендации

### 16. Docker hardening для эмулятора

```yaml
android-emulator:
  security_opt:
    - no-new-privileges:true
  read_only: true
  tmpfs:
    - /tmp
    - /run
    - /var/run
  cap_drop:
    - ALL
```

### 17. Отдельный SSH-ключ для Gradle cache

Текущий `VPS_SSH_KEY` используется для deploy. Создать отдельный `VPS_GRADLE_KEY` с ограничением в `authorized_keys`:

```
command="rrsync -wo /opt/gradle-cache/",no-pty,no-port-forwarding ssh-ed25519 AAAA...
```

Ограничивает ключ до write-only rsync в конкретную директорию.

### 18. Gradle cache sync — ограничить scope

Sync только `jars-*` и `transforms-*/`, НЕ `build-cache-1/` (содержит task outputs, может быть отравлен). Gradle build cache server (HTTP) криптографически верифицирует записи — более безопасен чем rsync.

---

## Отклонённые идеи

| Идея | Почему отклонена |
|------|-----------------|
| `budtmo/docker-android` | Нет API 35 (PR #490 не смержен с Feb 2025) |
| Google Jetstream | Overkill — для CI ферм, не для dev |
| `scrcpy` over WebSocket | Нужен отдельный контейнер, нет авторизации |
| Remote build cache server (HTTP) | `setup-gradle` уже даёт shared CI cache; defer до реальной потребности |
| `fetch-depth: 1` для build jobs | Ломает git-based versioning |
| Configuration cache `problems=fail` | 3 плагина несовместимы; `warn` — единственный рабочий вариант пока KAPT не удалён |

---

## Приоритизированный план действий

| Приоритет | Действие | Влияние | Усилие |
|-----------|----------|---------|--------|
| P0 | Заменить `actions/cache` → `setup-gradle@v4` + encrypted config cache | HIGH | Low |
| P0 | Убрать `http://176.9.0.156:6080` из спеки, добавить SSH tunnel / Caddy auth | CRITICAL | Trivial |
| P0 | Добавить `group_add: "kvm"` в compose | HIGH (блокер) | Trivial |
| P1 | KAPT → KSP миграция | HIGH | Low |
| P1 | Blacksmith runners | HIGH | Trivial |
| P1 | JVM heap 4GB + G1GC tuning | MEDIUM | Low |
| P1 | Skip build-release на PR | MEDIUM | Trivial |
| P2 | Прегенерация protobuf | MEDIUM | Low |
| P2 | `fetch-depth: 0` для build jobs | N/A (correctness) | Trivial |
| P2 | Docker hardening (no-new-privileges, read_only, cap_drop) | MEDIUM | Low |
| P2 | Отдельный SSH ключ для Gradle cache | MEDIUM | Low |
| P3 | SSH build aliases (gradle-build, gradle-install) | MEDIUM (DX) | Low |
| P3 | `scrcpy` + `ghapk` + `gh run watch` | LOW (DX) | Trivial |
| P3 | Syncthing sync `mobile/` | LOW (DX) | Medium |
| P3 | ntfy уведомления | LOW (DX) | Low |
| P3 | Pre-push hook на dedic | LOW (DX) | Low |
| P4 | Emulator на dedic (Docker + KVM + noVNC) | LOW (DX) | High |
| P4 | `dorny/paths-filter` внутри Android workflow | LOW | Low |
| P4 | Delete no-op cleanup job | Trivial | Trivial |
