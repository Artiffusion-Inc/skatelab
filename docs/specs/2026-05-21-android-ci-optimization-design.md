# Android CI & Development Optimization

> **Goal:** Ускорить CI→APK цикл, снизить RAM-нагрузку локально, дать UI-проверку без телефона через эмулятор на dedic.

**Architecture:** CI-first подход. Blacksmith runners + `gradle/actions/setup-gradle` + encrypted configuration cache. KSP вместо KAPT. Прегенерация protobuf. Эмулятор в Docker на dedic через noVNC (только через SSH tunnel / Cloudflare Access). APK из CI → `adb install` по USB.

**Tech Stack:** GitHub Actions (Blacksmith), Gradle 8.14, Android SDK 35, Docker + KVM (dedic), noVNC, KSP

**Review report:** `docs/specs/2026-05-21-android-ci-optimization-report.md`

---

## 1. CI Optimizations

### 1.1 Blacksmith runners

Заменить `ubuntu-latest` → Blacksmith runners. Разное количество vCPU по job:

| Job | Runner | Обоснование |
|-----|--------|-------------|
| `lint` | `blacksmith-2vcpu-ubuntu-2404` | ktlint однопоточный |
| `test` | `blacksmith-2vcpu-ubuntu-2404` | Unit tests, `maxParallelForks=1` |
| `build-debug` | `blacksmith-4vcpu-ubuntu-2404` | Compose compiler + KSP CPU-intensive |
| `build-release` | `blacksmith-4vcpu-ubuntu-2404` | R8/ProGuard CPU-intensive, 16GB RAM |

### 1.2 `gradle/actions/setup-gradle@v4` вместо `actions/cache`

Заменить `actions/cache@v4` в composite action на `setup-gradle@v4` с encrypted configuration cache. Причины:
- `setup-gradle` кэширует: dependency jars, build-cache, configuration-cache (зашифрованный), generated-gradle-jars
- Intelligent cleanup (prunes stale entries, deduplicates)
- `cache-read-only` для PR из форков (предотвращает cache poisoning)
- Dependency graph generation (Dependabot-like alerts)

Секрет `GRADLE_CACHE_ENCRYPTION_KEY` — `openssl rand -base64 16`, хранится в GitHub Secrets.

Composite action:
```yaml
# .github/actions/setup-android/action.yml
name: "Setup Android SDK + Gradle"
description: "JDK 17, Gradle setup with config cache"

inputs:
  java-version:
    description: "JDK version"
    default: "17"
  cache-encryption-key:
    description: "Gradle configuration cache encryption key"
    required: false

runs:
  using: "composite"
  steps:
    - uses: actions/setup-java@v5
      with:
        distribution: temurin
        java-version: ${{ inputs.java-version }}

    - uses: gradle/actions/setup-gradle@v4
      with:
        cache-encryption-key: ${{ inputs.cache-encryption-key }}

    - name: Gradle CI tuning
      shell: bash
      working-directory: mobile
      run: |
        cat >> gradle.properties <<'EOF'
        org.gradle.daemon=false
        org.gradle.parallel=true
        org.gradle.caching=true
        org.gradle.configuration-cache=true
        org.gradle.configuration-cache.problems=warn
        EOF
```

### 1.3 Configuration cache + совместимость плагинов

`gradle.properties`:
```properties
org.gradle.configuration-cache=true
org.gradle.configuration-cache.problems=warn
org.gradle.configuration-cache.parallel=true
```

Совместимость (по результатам аудита):

| Plugin | Compatible | Примечание |
|--------|-----------|------------|
| `com.android.application` 8.9.1 | Partial | AGP 8.9+ в основном совместим |
| `org.jetbrains.kotlin.android` 2.1.21 | Yes | K2 backend |
| `org.jetbrains.kotlin.kapt` 2.1.21 | **No** | Убирается → KSP (см. 1.4) |
| `org.jetbrains.kotlin.plugin.compose` 2.1.21 | Yes | Новый Compose compiler plugin |
| `com.google.dagger.hilt.android` 2.56.1 | Partial | С KSP совместим лучше |
| `com.google.protobuf` 0.9.5 | **No** | Убирается → прегенерация (см. 1.5) |
| `org.jlleitschuh.gradle.ktlint` 12.2.0 | No | Не влияет на `assembleDebug` (не в task graph) |

С KSP + прегенерацией protobuf единственный оставшийся warning — ktlint, но он не в task graph для `assembleDebug` → cache entry сохраняется.

### 1.4 KAPT → KSP миграция

Hilt 2.56.1 официально поддерживает KSP (с версии 2.48). В проекте один KAPT processor — Hilt compiler.

**Шаги:**
1. `mobile/build.gradle.kts`: заменить `kapt` plugin → `ksp`:
   ```kotlin
   // REMOVE: id("org.jetbrains.kotlin.kapt") version "2.1.21" apply false
   // ADD:
   id("com.google.devtools.ksp") version "2.1.21-1.0.29" apply false
   ```

2. `mobile/app/build.gradle.kts`:
   ```kotlin
   // REMOVE: id("org.jetbrains.kotlin.kapt")
   // ADD: id("com.google.devtools.ksp")

   // REPLACE: kapt("com.google.dagger:hilt-android-compiler:2.56.1")
   // WITH:    ksp("com.google.dagger:hilt-android-compiler:2.56.1")
   ```

3. `mobile/gradle.properties` добавить:
   ```properties
   ksp.project.isolation.enabled=true
   ```

**Влияние:** 15-25% быстрее инкрементальные сборки. Убирает KAPT как config-cache blocker. Меньше GC pressure (нет Java stub generation).

### 1.5 Прегенерация Protobuf источников

`imu.proto` — 3 сообщения, меняется крайне редко. Protobuf plugin 0.9.5 — hard blocker для configuration cache (issue #687, нет фикса).

**Шаги:**
1. Один раз: `./gradlew :app:generateDebugProto`
2. Скопировать `app/build/generated/source/proto/debug/ru/skatelab/capture/proto/` → `app/src/main/java/ru/skatelab/capture/proto/`
3. Убрать `com.google.protobuf` plugin из обоих `build.gradle.kts`
4. Убрать `protobuf { ... }` блок из `app/build.gradle.kts`
5. Убрать `implementation("com.google.protobuf:protobuf-javalite:4.30.2")` (сгенерированные sources включают runtime)

**Влияние:** Убирает второй config-cache blocker. Убирает `protoc` binary download. Хранить `.proto` файл в репо для документации.

### 1.6 JVM heap tuning

```properties
# CI (4vcpu, 16GB RAM) и локально
org.gradle.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=256m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g

# Kotlin daemon (отдельный JVM)
kotlin.daemon.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g

# AndroidX
android.useAndroidX=true
kotlin.code.style=official
android.nonTransitiveRClass=true

# Parallelism + caching
org.gradle.parallel=true
org.gradle.caching=true

# Configuration cache
org.gradle.configuration-cache=true
org.gradle.configuration-cache.problems=warn
org.gradle.configuration-cache.parallel=true

# KSP project isolation (required for config cache + KSP)
ksp.project.isolation.enabled=true
```

Dedic override (`~/.gradle/gradle.properties`):
```properties
org.gradle.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -XX:+HeapDumpOnOutOfMemoryError -Xmx6g -Xms6g
org.gradle.workers.max=8
```

Ключевые параметры:
- `-Xmx4g`: Sweet spot для Compose+KSP (2g вызывает частые GC pauses)
- `-Xms4g`: Pre-allocate heap, без runtime growth pauses
- `-XX:+UseG1GC`: Лучше pause times чем ParallelGC
- `-XX:SoftRefLRUPolicyMSPerMB=1`: Collect SoftRefs за ~4s вместо ~51min (default 1000ms/MB)
- `-XX:ReservedCodeCacheSize=256m`: Gradle загружает тысячи классов
- **НЕ** ставить `MaxMetaspaceSize` на JDK 17+ (по анализу Jason Pearson)

### 1.7 APK versioning из git

Требует `fetch-depth: 0` в build jobs (shallow clone даёт неверный `versionCode`).

```kotlin
android {
    defaultConfig {
        versionCode = providers.exec {
            commandLine("git", "rev-list", "--count", "HEAD")
        }.standardOutput.asText.get().trim().toInt()
        versionName = providers.exec {
            commandLine("git", "describe", "--tags", "--always", "--dirty")
        }.standardOutput.asText.get().trim()
    }
}
```

### 1.8 Skip build-release на PR

```yaml
build-release:
  if: github.event_name == 'push' && github.ref == 'refs/heads/master'
```

`assembleRelease` с R8 = 2-3x дольше debug. Для PR достаточно debug APK. Release build можно запустить вручную через `workflow_dispatch`.

### 1.9 APK в PR comment

После `build-debug` job — бот пишет ссылку на артефакт в PR. Используя `actions/github-script@v7`.

### 1.10 Path-based job skipping

Добавить `changes` job с `dorny/paths-filter@v3` (уже используется в `ci-reusable.yml`):
- `kotlin`: `mobile/**/*.kt`, `mobile/**/*.java`, `mobile/**/*.xml`
- `gradle`: `mobile/**/build.gradle.kts`, `mobile/gradle/**`, `mobile/gradle.properties`

lint/test → только при kotlin изменениях. build-debug → при kotlin ИЛИ gradle.

### 1.11 fetch-depth

- `lint`, `test`: `fetch-depth: 1` (история не нужна)
- `build-debug`, `build-release`: `fetch-depth: 0` (git-based versioning + config cache fingerprinting)

---

## 2. Dedic: Gradle Cache Sync

### 2.1 SSH-based cache sync с ограничениями

Выбран SSH подход вместо отдельного Gradle build cache server — проще, нет отдельного сервиса.

**Безопасность:**
- Отдельный SSH-ключ `VPS_GRADLE_KEY` (не `VPS_SSH_KEY`)
- Ограничение в `authorized_keys` на dedic:
  ```
  command="rrsync -wo /opt/gradle-cache/",no-pty,no-X11-forwarding,no-port-forwarding ssh-ed25519 AAAA...
  ```
- Sync только `jars-*` и `transforms-*/`, НЕ `build-cache-1/` (task outputs могут быть отравлены)

**CI step:**
```yaml
- name: Sync Gradle cache to dedic
  if: success()
  run: |
    rsync -az --include='jars-*/' --include='transforms-*/' --exclude='*' \
      ~/.gradle/caches/ dev@${{ secrets.VPS_HOST }}:/opt/gradle-cache/
  env:
    SSH_PRIVATE_KEY: ${{ secrets.VPS_GRADLE_KEY }}
```

---

## 3. Dedic: Android Emulator

### 3.1 Docker + KVM + noVNC

Custom Containerfile (не `budtmo/docker-android` — нет API 35, PR #490 не смержен с Feb 2025).

```dockerfile
FROM docker.io/library/ubuntu:24.04
ENV ANDROID_HOME=/opt/android-sdk

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk-headless unzip curl wget xz-utils \
    libgl1-mesa-dri libgl1-mesa-glx dbus-x11 \
    novnc websockify supervisor \
    && rm -rf /var/lib/apt/lists/*

# Android SDK
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools \
    && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11006723_latest.zip -o /tmp/cmdtools.zip \
    && unzip /tmp/cmdtools.zip -d ${ANDROID_HOME}/cmdline-tools \
    && mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest \
    && rm /tmp/cmdtools.zip

RUN yes | ${ANDROID_HOME}/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" \
    "platforms;android-35" \
    "build-tools;35.0.0" \
    "system-images;android-35;google_apis;x86_64" \
    "emulator"

# AVD (pixel_6 profile вместо устаревшего -d 17)
RUN ${ANDROID_HOME}/cmdline-tools/latest/bin/avdmanager create avd \
    -n skatelab -k "system-images;android-35;google_apis;x86_64" -d "pixel_6"

# Disable ADB TCP listening (безопасность)
RUN mkdir -p /root/.android/avd/skatelab.avd && \
    echo "hw.adbPort=0" >> /root/.android/avd/skatelab.avd/config.ini

# noVNC + supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
EXPOSE 6080

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

### 3.2 Доступ (ТОЛЬКО через авторизованный канал)

**НЕ** открывать `http://176.9.0.156:6080` напрямую. noVNC не имеет встроенной авторизации.

**Способ 1 — SSH tunnel (рекомендуется):**
```bash
ssh -L 6080:127.0.0.1:6080 -p 43210 dev@176.9.0.156
# Затем открыть http://localhost:6080 в браузере
```

**Способ 2 — Caddy route с Cloudflare Access:**
```
emu.skatelab.ru {
    # Cloudflare Access handles auth at the edge
    reverse_proxy android-emulator:6080
}
```
Cloudflare Access: SSO auth (Google/GitHub), audit logs, MFA, email domain restriction.

**Способ 3 — Caddy route с basic_auth (фоллбек):**
```
emu.skatelab.ru {
    basic_auth {
        admin $2a$14$<bcrypt_hash>
    }
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }
    reverse_proxy android-emulator:6080
}
```

Caddy 2.x нативно проксирует WebSocket (noVNC). `flush_interval` не нужен.

**ADB:** Только через `docker exec`:
```bash
docker exec android-emulator adb install /apk/app-debug.apk
```

Порт 5555 НЕ публиковать. ADB на эмуляторных образах даёт root shell.

### 3.3 Compose интеграция

```yaml
android-emulator:
  build: /opt/skatelab/android-emulator
  restart: unless-stopped
  ports:
    - "127.0.0.1:6080:6080"   # noVNC (только через Caddy/SSH tunnel)
    # НЕ публиковать 5555 (ADB)
  devices:
    - /dev/kvm:/dev/kvm
  group_add:
    - "kvm"                    # GID = getent group kvm на хосте
  security_opt:
    - no-new-privileges:true
  read_only: true
  tmpfs:
    - /tmp
    - /run
    - /var/run
  cap_drop:
    - ALL
  volumes:
    - android-avd:/root/.android/avd
    - /opt/skatelab/apk:/apk:ro   # APK drop zone
    - /opt/gradle-cache:/root/.gradle:cached  # Shared Gradle cache
  environment:
    - EMULATOR_DEVICE=pixel_6
    - WEB_VNC=true
  deploy:
    resources:
      limits:
        memory: 4G
        cpus: "2.0"
      reservations:
        memory: 2G
        devices:
          - capabilities: ["kvm"]
  healthcheck:
    test: ["CMD-SHELL", "adb wait-for-device && adb shell getprop sys.boot_completed | grep -q 1"]
    interval: 30s
    timeout: 10s
    retries: 10
    start_period: 120s    # Emulator boot ~60-90s with KVM
  networks:
    - infra
```

### 3.4 Ресурсы

- RAM: 4 GB (лимит), 2 GB (reservation)
- Disk: ~8-10 GB (SDK + system image + AVD data)
- CPU: 2 cores (лимит), KVM acceleration
- На dedic 62GB RAM, ~57GB свободно — запас огромный

---

## 4. Developer Workflow

### 4.1 Daily development (оптимальный цикл)

1. Редактируешь код локально (Neovim/helix)
2. **Quick check:** standalone `ktlint` binary (~200MB, нет Gradle daemon, ~3s)
3. **Build:** SSH build alias → `ssh dedic "./gradlew assembleDebug"` (62GB RAM, ~2-3 min с warm cache)
4. **Install на телефон:** `scp dedic:/opt/skatelab/mobile/app/build/outputs/apk/debug/app-debug.apk /tmp/ && adb install -r /tmp/app-debug.apk`
5. **Или ADB over SSH tunnel:** `ssh -R 5037:localhost:5037 dedic` → dedic `adb install`直达 local phone
6. **UI preview:** `scrcpy` mirrors phone screen (~20ms latency, keyboard/mouse control)

Shell aliases:
```bash
alias gradle-build='ssh dedic "cd /opt/skatelab/mobile && ./gradlew assembleDebug"'
alias gradle-install='scp dedic:/opt/skatelab/mobile/app/build/outputs/apk/debug/app-debug.apk /tmp/app-debug.apk && adb install -r /tmp/app-debug.apk'
alias gradle-deploy='gradle-build && gradle-install'
```

### 4.2 CI workflow

1. Push → CI собирает APK (~2-4 min с оптимизациями)
2. APK ссылка в PR comment (bot)
3. Quick download: `ghapk` alias → `gh run download` + `adb install`
4. ntfy уведомление когда CI завершён (dedic уже запускает `infra-ntfy-1`)

```bash
# One-command APK download + install
ghapk() {
  local run_id=$(gh run list --workflow=android.yml --limit=1 --json databaseId --jq '.[0].databaseId')
  gh run download "$run_id" -n apk-debug -D /tmp/apk-download 2>/dev/null
  adb install -r /tmp/apk-download/app-debug.apk
}

# Watch CI until complete
alias watch-android='gh run watch $(gh run list --workflow=android.yml --limit=1 --json databaseId --jq ".[0].databaseId")'
```

### 4.3 UI без телефона

1. SSH tunnel: `ssh -L 6080:127.0.0.1:6080 -p 43210 dev@176.9.0.156`
2. Открыть `http://localhost:6080` → noVNC → эмулятор Android
3. `docker exec android-emulator adb install /apk/app-debug.apk`
4. Проверяешь UI

### 4.4 Код-синхронизация с dedic

**Способ 1 — Git pull (простой):**
```bash
git push && ssh dedic "cd /opt/skatelab && git pull"
```

**Способ 2 — Syncthing (автоматический):**
Dedic уже запускает `infra-syncthing-1`. Настроить bidirectional sync `mobile/` — код синхронизируется за 5-15 сек.

### 4.5 Pre-push hook

Git hook запускает `ktlintCheck` на dedic, блокирует push при ошибке:
```bash
# .git/hooks/pre-push
#!/bin/sh
echo "Running ktlint on dedic..."
ssh dedic "cd /opt/skatelab/mobile && ./gradlew ktlintCheck" || {
  echo "ktlint failed. Fix before pushing."
  exit 1
}
```

### 4.6 Ограничение: Compose Live Edit

Compose Live Edit — Android Studio-only функция. Нет CLI эквивалента, нет Gradle task. Google привязал к IDE. Это фундаментальное ограничение CLI-разработки — минимальный цикл UI-итерации = ~2-3 min (build + install).

---

## 5. Security Summary

| Угроза | Риск | Митигация |
|--------|------|-----------|
| noVNC без авторизации | CRITICAL | SSH tunnel / Cloudflare Access / Caddy basic_auth |
| ADB port 5555 exposed | HIGH | Не публиковать порт, `hw.adbPort=0` в AVD config |
| Gradle cache poisoning | MEDIUM | Отдельный SSH ключ с `rrsync`, sync только `jars-*` + `transforms-*/` |
| KVM container escape | LOW-MEDIUM | `no-new-privileges`, `read_only`, `cap_drop: ALL`, trusted image |
| SSH key overuse | MEDIUM | Отдельный `VPS_GRADLE_KEY` для cache sync |
| noVNC WebSocket hijack | MEDIUM | Caddy basic_auth / Cloudflare Access |
| Cache data leakage | LOW | Gradle cache содержит compiled code, server must be secured |

Новых открытых портов на firewall не нужно. Порт 6080 привязан к `127.0.0.1`, Caddy проксирует через Docker bridge.
