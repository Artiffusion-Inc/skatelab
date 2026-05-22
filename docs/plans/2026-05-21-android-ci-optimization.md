# Android CI & Development Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ускорить Android CI, убрать KAPT/KSP blocker для configuration cache, настроить эмулятор на dedic для UI-проверки.

**Architecture:** 3 волны: (1) Gradle build optimizations (KSP, JVM tuning, protobuf pregen, config cache), (2) CI workflow rewrite (Blacksmith, setup-gradle, path filters, release gating), (3) Dedic infrastructure (emulator Docker container, Caddy route, cache sync).

**Tech Stack:** Gradle 8.14, KSP 2.1.21-1.0.29, GitHub Actions (Blacksmith), Docker + KVM, noVNC

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `mobile/gradle.properties` | Modify | JVM heap, config cache, KSP isolation, parallel/caching flags |
| `mobile/build.gradle.kts` | Modify | Replace kapt → ksp plugin, remove protobuf plugin |
| `mobile/app/build.gradle.kts` | Modify | Replace kapt → ksp, remove protobuf block, git versioning |
| `mobile/app/src/main/proto/imu.proto` | Keep | Source of truth for proto schema (documentation) |
| `mobile/app/src/main/java/ru/skatelab/capture/proto/` | Create | Pre-generated protobuf Java Lite sources |
| `.github/actions/setup-android/action.yml` | Modify | Replace actions/cache → setup-gradle@v4, add encryption key input |
| `.github/workflows/android.yml` | Modify | Blacksmith runners, changes job, release gating, fetch-depth |
| `infra/android-emulator/Containerfile` | Create | Android SDK 35 + emulator + noVNC + supervisor |
| `infra/android-emulator/supervisord.conf` | Create | Xvfb + emulator + adb server + websockify + noVNC |
| `infra/compose.prod.yaml` | Modify | Add android-emulator service |
| `infra/Caddyfile` | Modify | Add emu.skatelab.ru route with basic_auth |

---

## Wave 1: Gradle Build Optimizations

### Task 1: KAPT → KSP Migration

**Files:**

- Modify: `mobile/build.gradle.kts`
- Modify: `mobile/app/build.gradle.kts`

- [ ] **Step 1: Update root build.gradle.kts — replace kapt plugin with ksp**

In `mobile/build.gradle.kts`, replace line 5 and add ksp:

```kotlin
plugins {
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.1.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.21" apply false
    id("com.google.devtools.ksp") version "2.1.21-1.0.29" apply false
    id("com.google.dagger.hilt.android") version "2.56.1" apply false
    id("com.google.protobuf") version "0.9.5" apply false
    id("org.jlleitschuh.gradle.ktlint") version "12.2.0" apply false
}
```

- [ ] **Step 2: Update app build.gradle.kts — replace kapt with ksp**

In `mobile/app/build.gradle.kts`, replace plugin on line 4:

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.dagger.hilt.android")
    id("com.google.protobuf")
    id("org.jlleitschuh.gradle.ktlint") version "12.2.0"
}
```

And in dependencies block (line 94), replace:

```kotlin
    // Hilt
    implementation("com.google.dagger:hilt-android:2.56.1")
    ksp("com.google.dagger:hilt-android-compiler:2.56.1")
    implementation("androidx.hilt:hilt-navigation-compose:1.2.0")
```

- [ ] **Step 3: Verify build succeeds**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL. Hilt generates sources via KSP instead of KAPT.

- [ ] **Step 4: Commit**

```bash
git add mobile/build.gradle.kts mobile/app/build.gradle.kts
git commit -m "refactor(mobile): migrate Hilt from KAPT to KSP"
```

---

### Task 2: Pre-generate Protobuf Sources

**Files:**

- Create: `mobile/app/src/main/java/ru/skatelab/capture/proto/` (generated Java files)
- Modify: `mobile/build.gradle.kts`
- Modify: `mobile/app/build.gradle.kts`

- [ ] **Step 1: Generate protobuf Java Lite sources**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew :app:generateDebugProto`
Expected: Sources generated in `app/build/generated/source/proto/debug/ru/skatelab/capture/proto/`

- [ ] **Step 2: Copy generated sources into source tree**

Run:
```bash
mkdir -p /home/michael/Github/skating-biomechanics-ml/mobile/app/src/main/java/ru/skatelab/capture/proto/
cp /home/michael/Github/skating-biomechanics-ml/mobile/app/build/generated/source/proto/debug/ru/skatelab/capture/proto/* /home/michael/Github/skating-biomechanics-ml/mobile/app/src/main/java/ru/skatelab/capture/proto/
```

- [ ] **Step 3: Remove protobuf plugin from root build.gradle.kts**

In `mobile/build.gradle.kts`, remove line with protobuf plugin:

```kotlin
plugins {
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.1.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.21" apply false
    id("com.google.devtools.ksp") version "2.1.21-1.0.29" apply false
    id("com.google.dagger.hilt.android") version "2.56.1" apply false
    id("org.jlleitschuh.gradle.ktlint") version "12.2.0" apply false
}
```

- [ ] **Step 4: Remove protobuf plugin and block from app build.gradle.kts**

In `mobile/app/build.gradle.kts`, remove `id("com.google.protobuf")` from plugins block.

Remove the entire `protobuf { ... }` block (lines 59-73).

Remove the dependency:
```kotlin
    // REMOVE: implementation("com.google.protobuf:protobuf-javalite:4.30.2")
```

- [ ] **Step 5: Verify build succeeds without protobuf plugin**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL. Proto classes found from checked-in sources.

- [ ] **Step 6: Commit**

```bash
git add mobile/build.gradle.kts mobile/app/build.gradle.kts mobile/app/src/main/java/ru/skatelab/capture/proto/
git commit -m "refactor(mobile): pre-generate protobuf sources, remove plugin"
```

---

### Task 3: JVM Heap Tuning + Configuration Cache

**Files:**

- Modify: `mobile/gradle.properties`

- [ ] **Step 1: Replace gradle.properties with optimized version**

Write to `mobile/gradle.properties`:

```properties
org.gradle.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=256m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g
kotlin.daemon.jvmargs=-Dfile.encoding=UTF-8 -XX:+UseG1GC -XX:SoftRefLRUPolicyMSPerMB=1 -XX:ReservedCodeCacheSize=320m -XX:+HeapDumpOnOutOfMemoryError -Xmx4g -Xms4g
android.useAndroidX=true
kotlin.code.style=official
android.nonTransitiveRClass=true
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.configuration-cache.problems=warn
org.gradle.configuration-cache.parallel=true
ksp.project.isolation.enabled=true
```

- [ ] **Step 2: Verify build with configuration cache**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL. May show configuration cache warnings from ktlint plugin (acceptable).

- [ ] **Step 3: Verify second build uses configuration cache**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew assembleDebug`
Expected: "Configuration cache entry reused" in output. Build significantly faster.

- [ ] **Step 4: Commit**

```bash
git add mobile/gradle.properties
git commit -m "perf(mobile): JVM heap 4g + G1GC + configuration cache + KSP isolation"
```

---

### Task 4: Git-based APK Versioning

**Files:**

- Modify: `mobile/app/build.gradle.kts`

- [ ] **Step 1: Replace static versioning with git-based**

In `mobile/app/build.gradle.kts`, replace lines 17-18 (`versionCode = 1`, `versionName = "1.0.0"`) with:

```kotlin
        versionCode = providers.exec {
            commandLine("git", "rev-list", "--count", "HEAD")
        }.standardOutput.asText.get().trim().toInt()
        versionName = providers.exec {
            commandLine("git", "describe", "--tags", "--always", "--dirty")
        }.standardOutput.asText.get().trim()
```

- [ ] **Step 2: Verify version is derived from git**

Run: `cd /home/michael/Github/skating-biomechanics-ml/mobile && ./gradlew assembleDebug 2>&1 | grep -i version`
Expected: Build succeeds, versionCode reflects git commit count.

- [ ] **Step 3: Commit**

```bash
git add mobile/app/build.gradle.kts
git commit -m "feat(mobile): git-based versionCode and versionName"
```

---

## Wave 2: CI Workflow Rewrite

### Task 5: Replace Composite Action with setup-gradle@v4

**Files:**

- Modify: `.github/actions/setup-android/action.yml`

- [ ] **Step 1: Rewrite composite action**

Write to `.github/actions/setup-android/action.yml`:

```yaml
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

- [ ] **Step 2: Commit**

```bash
git add .github/actions/setup-android/action.yml
git commit -m "ci(android): replace actions/cache with setup-gradle@v4 + encrypted config cache"
```

---

### Task 6: Rewrite Android Workflow

**Files:**

- Modify: `.github/workflows/android.yml`

- [ ] **Step 1: Write complete workflow**

Write to `.github/workflows/android.yml`:

```yaml
name: Android CI

on:
  push:
    branches: [master]
    paths:
      - "mobile/**"
      - ".github/workflows/android.yml"
      - ".github/actions/setup-android/**"
  pull_request:
    branches: [master]
    paths:
      - "mobile/**"
      - ".github/workflows/android.yml"
      - ".github/actions/setup-android/**"
  workflow_dispatch:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  changes:
    name: Detect changes
    runs-on: blacksmith-2vcpu-ubuntu-2404
    outputs:
      kotlin: ${{ steps.filter.outputs.kotlin }}
      gradle: ${{ steps.filter.outputs.gradle }}
    steps:
      - uses: actions/checkout@v5
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            kotlin:
              - "mobile/**/*.kt"
              - "mobile/**/*.java"
              - "mobile/**/*.xml"
            gradle:
              - "mobile/**/build.gradle.kts"
              - "mobile/gradle/**"
              - "mobile/gradle.properties"

  lint:
    needs: [changes]
    if: needs.changes.outputs.kotlin == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 1
      - uses: ./.github/actions/setup-android
        with:
          cache-encryption-key: ${{ secrets.GRADLE_CACHE_ENCRYPTION_KEY }}
      - run: ./gradlew ktlintCheck

  test:
    needs: [changes]
    if: needs.changes.outputs.kotlin == 'true'
    runs-on: blacksmith-2vcpu-ubuntu-2404
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 1
      - uses: ./.github/actions/setup-android
        with:
          cache-encryption-key: ${{ secrets.GRADLE_CACHE_ENCRYPTION_KEY }}
      - run: ./gradlew testDebugUnitTest

  build-debug:
    needs: [changes]
    if: needs.changes.outputs.kotlin == 'true' || needs.changes.outputs.gradle == 'true'
    runs-on: blacksmith-4vcpu-ubuntu-2404
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: ./.github/actions/setup-android
        with:
          cache-encryption-key: ${{ secrets.GRADLE_CACHE_ENCRYPTION_KEY }}
      - run: ./gradlew assembleDebug
      - uses: actions/upload-artifact@v4
        with:
          name: apk-debug
          path: mobile/app/build/outputs/apk/debug/app-debug.apk
          retention-days: 14
      - name: Comment PR with APK link
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const artifactUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.pull_request.number,
              body: `📱 Debug APK: [Download from Artifacts](${artifactUrl}) (look for \`apk-debug\`)`
            });

  build-release:
    needs: [lint, test]
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    runs-on: blacksmith-4vcpu-ubuntu-2404
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - uses: ./.github/actions/setup-android
        with:
          cache-encryption-key: ${{ secrets.GRADLE_CACHE_ENCRYPTION_KEY }}
      - run: ./gradlew assembleRelease
      - uses: actions/upload-artifact@v4
        with:
          name: apk-release
          path: mobile/app/build/outputs/apk/release/app-release.apk
          retention-days: 90

  ci-passed:
    name: Android CI Summary
    runs-on: blacksmith-2vcpu-ubuntu-2404
    needs: [changes, lint, test, build-debug, build-release]
    if: always()
    outputs:
      result: ${{ steps.check.outputs.result }}
    steps:
      - name: Check results
        id: check
        run: |
          if [[ "${{ needs.lint.result }}" == "failure" ]] || \
             [[ "${{ needs.test.result }}" == "failure" ]] || \
             [[ "${{ needs.build-debug.result }}" == "failure" ]] || \
             [[ "${{ needs.build-release.result }}" == "failure" ]]; then
            echo "result=failure" >> "$GITHUB_OUTPUT"
            exit 1
          fi
          echo "result=success" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Create GRADLE_CACHE_ENCRYPTION_KEY secret**

Run locally:
```bash
openssl rand -base64 16
```

Save the output. Add to GitHub repo: Settings → Secrets and variables → Actions → New repository secret → Name: `GRADLE_CACHE_ENCRYPTION_KEY`, Value: (paste output).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/android.yml
git commit -m "ci(android): Blacksmith runners, setup-gradle, path filters, release gating"
```

---

## Wave 3: Dedic Infrastructure

### Task 7: Create Android Emulator Docker Image

**Files:**

- Create: `infra/android-emulator/Containerfile`
- Create: `infra/android-emulator/supervisord.conf`

- [ ] **Step 1: Create Containerfile**

Write to `infra/android-emulator/Containerfile`:

```dockerfile
FROM docker.io/library/ubuntu:24.04
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH="${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

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

RUN yes | sdkmanager \
    "platform-tools" \
    "platforms;android-35" \
    "build-tools;35.0.0" \
    "system-images;android-35;google_apis;x86_64" \
    "emulator"

# AVD
RUN avdmanager create avd \
    -n skatelab -k "system-images;android-35;google_apis;x86_64" -d "pixel_6"

# Disable ADB TCP listening (security: no remote ADB)
RUN mkdir -p /root/.android/avd/skatelab.avd && \
    echo "hw.adbPort=0" >> /root/.android/avd/skatelab.avd/config.ini

# noVNC + supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
EXPOSE 6080

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

- [ ] **Step 2: Create supervisord.conf**

Write to `infra/android-emulator/supervisord.conf`:

```ini
[supervisord]
nodaemon=true

[program:xvfb]
command=/usr/bin/Xvfb :0 -screen 0 1280x800x24 -ac
autorestart=true

[program:emulator]
command=/opt/android-sdk/emulator/emulator @skatelab -no-window -gpu swiftshader_indirect -noaudio -no-boot-anim -accel on
environment=DISPLAY=":0"
autorestart=true
startsecs=60

[program:adb-server]
command=/opt/android-sdk/platform-tools/adb wait-for-device
autorestart=true

[program:websockify]
command=/usr/bin/websockify --web /usr/share/novnc 6080 localhost:5900
autorestart=true

[program:x11vnc]
command=/usr/bin/x11vnc -display :0 -forever -shared -rfbport 5900 -nopw
environment=DISPLAY=":0"
autorestart=true
```

- [ ] **Step 3: Commit**

```bash
git add infra/android-emulator/
git commit -m "feat(infra): Android emulator Docker image with KVM + noVNC"
```

---

### Task 8: Add Emulator to Compose + Caddy Route

**Files:**

- Modify: `infra/compose.prod.yaml`
- Modify: `infra/Caddyfile`

- [ ] **Step 1: Add android-emulator service to compose.prod.yaml**

Append before `volumes:` section in `infra/compose.prod.yaml`:

```yaml
  android-emulator:
    build: /opt/skatelab/android-emulator
    restart: unless-stopped
    ports:
      - "127.0.0.1:6080:6080"
    devices:
      - /dev/kvm:/dev/kvm
    group_add:
      - "kvm"
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
      - /opt/skatelab/apk:/apk:ro
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: "2.0"
        reservations:
          memory: 2G
    healthcheck:
      test: ["CMD-SHELL", "/opt/android-sdk/platform-tools/adb wait-for-device && /opt/android-sdk/platform-tools/adb shell getprop sys.boot_completed | grep -q 1"]
      interval: 30s
      timeout: 10s
      retries: 10
      start_period: 120s
    networks:
      - infra
```

Add `android-avd:` to the `volumes:` section.

- [ ] **Step 2: Add Caddy route for emulator**

In `infra/Caddyfile`, add before the `skatelab.ru` block:

```
emu.skatelab.ru {
	basic_auth {
		admin $2a$14$qCujhVVkXSQPVUwRJunm8uYOgfiOM.Mox1K9lVoCQqWm1XieVs7DG
	}
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
	}
	reverse_proxy android-emulator:6080
}
```

Note: uses same bcrypt hash as `monitor.{$DOMAIN}` for `admin` user. Replace with a unique hash if preferred: `caddy hash-password --plaintext 'your-password'`.

- [ ] **Step 3: Commit**

```bash
git add infra/compose.prod.yaml infra/Caddyfile
git commit -m "feat(infra): android-emulator compose service + Caddy route with basic_auth"
```

---

### Task 9: Deploy Emulator to Dedic

**Files:** None (server-side operations)

- [ ] **Step 1: Verify KVM on dedic**

Run:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 'getent group kvm; ls -la /dev/kvm; free -h | head -2'
```

Expected: kvm group exists, `/dev/kvm` accessible, ~57GB free RAM.

- [ ] **Step 2: Create directories on dedic**

Run:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 'mkdir -p /opt/skatelab/android-emulator /opt/skatelab/apk'
```

- [ ] **Step 3: Copy emulator files to dedic**

Run:
```bash
scp -i ~/.ssh/id_rsa_remote_nopass -P 43210 \
  /home/michael/Github/skating-biomechanics-ml/infra/android-emulator/Containerfile \
  /home/michael/Github/skating-biomechanics-ml/infra/android-emulator/supervisord.conf \
  dev@176.9.0.156:/opt/skatelab/android-emulator/
```

- [ ] **Step 4: Build emulator image on dedic**

Run:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 \
  'cd /opt/skatelab && /usr/bin/docker compose build android-emulator'
```

Expected: Image builds successfully (~10-15 min first time for SDK download).

- [ ] **Step 5: Start emulator**

Run:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 \
  'cd /opt/skatelab && /usr/bin/docker compose up -d android-emulator'
```

- [ ] **Step 6: Wait for emulator to boot and verify**

Wait ~2 minutes, then:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 \
  '/usr/bin/docker exec skatelab-android-emulator-1 /opt/android-sdk/platform-tools/adb shell getprop sys.boot_completed'
```

Expected: `1`

- [ ] **Step 7: Test noVNC via SSH tunnel**

Run locally:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -L 6080:127.0.0.1:6080 -p 43210 dev@176.9.0.156
```

Open `http://localhost:6080` in browser. Expected: Android emulator UI visible.

- [ ] **Step 8: Test APK install**

Run:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 \
  '/usr/bin/docker exec skatelab-android-emulator-1 /opt/android-sdk/platform-tools/adb install /apk/app-debug.apk'
```

Note: Place a test APK in `/opt/skatelab/apk/` first, or this will fail with "file not found" — that's expected. The workflow works once APKs are placed there.

---

### Task 10: Gradle Cache SSH Key Setup

**Files:** None (server-side + GitHub secrets)

- [ ] **Step 1: Generate dedicated SSH key pair for Gradle cache sync**

Run:
```bash
ssh-keygen -t ed25519 -C "gradle-cache-ci" -f /tmp/gradle_cache_key -N ""
```

- [ ] **Step 2: Add public key to dedic with rrsync restriction**

Run:
```bash
# Find rrsync path on dedic
RRSYNC_PATH=$(ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 'which rrsync 2>/dev/null || find /usr/share/rsync -name rrsync 2>/dev/null | head -1')
echo "rrsync path: $RRSYNC_PATH"

# Add to authorized_keys with restriction
PUBKEY=$(cat /tmp/gradle_cache_key.pub)
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 \
  "echo 'command=\"${RRSYNC_PATH:-/usr/share/rsync/rrsync} -wo /opt/gradle-cache/\",no-pty,no-X11-forwarding,no-port-forwarding ${PUBKEY}' >> ~/.ssh/authorized_keys"
```

- [ ] **Step 3: Add private key as GitHub secret**

```bash
cat /tmp/gradle_cache_key | pbcopy  # or xclip -selection clipboard
```

Then: GitHub repo → Settings → Secrets → New secret → Name: `VPS_GRADLE_KEY`, Value: (paste private key).

- [ ] **Step 4: Create gradle-cache directory on dedic**

Run:
```bash
ssh -i ~/.ssh/id_rsa_remote_nopass -p 43210 dev@176.9.0.156 'mkdir -p /opt/gradle-cache'
```

- [ ] **Step 5: Clean up local temp key**

Run:
```bash
rm /tmp/gradle_cache_key /tmp/gradle_cache_key.pub
```

---

## Self-Review

**Spec coverage:**
- 1.1 Blacksmith runners → Task 6 ✓
- 1.2 setup-gradle@v4 → Task 5 ✓
- 1.3 Configuration cache → Task 3 ✓
- 1.4 KAPT → KSP → Task 1 ✓
- 1.5 Protobuf pregen → Task 2 ✓
- 1.6 JVM heap tuning → Task 3 ✓
- 1.7 Git versioning → Task 4 ✓
- 1.8 Skip release on PR → Task 6 ✓
- 1.9 APK in PR comment → Task 6 ✓
- 1.10 Path-based job skipping → Task 6 ✓
- 1.11 fetch-depth → Task 6 ✓
- 2.1 SSH cache sync → Task 10 ✓
- 3.1 Docker + KVM + noVNC → Task 7 ✓
- 3.2 Access (SSH tunnel / Caddy) → Task 8 + 9 ✓
- 3.3 Compose integration → Task 8 ✓
- 4.1-4.6 Developer workflow → Documented in spec, not code tasks (aliases are local dotfiles)

**Placeholder scan:** No TBD, TODO, or vague steps found.

**Type consistency:** KSP version `2.1.21-1.0.29` matches Kotlin `2.1.21`. Hilt version `2.56.1` consistent across all references. protobuf-javalite version `4.30.2` referenced only for removal.

**Gap:** Developer workflow aliases (section 4.1) are local dotfile changes, not repo changes. These are documented in the spec but not tracked as implementation tasks — the user applies them manually.
