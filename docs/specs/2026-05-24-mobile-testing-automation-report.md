# Mobile Testing Automation — Optimization Report

**Date:** 2026-05-24
**Base spec:** `docs/specs/2026-05-24-mobile-testing-automation-design.md`
**Server:** 176.9.0.156 (i7-6700, 4C/8T, 62 GB RAM, KVM, NVMe, Docker CE, ~19 production containers)

---

## Executive Summary

1. **Snapshots cut E2E cycle time by 60-70%** — named AVD snapshots with app pre-installed restore in 5-10s vs 30-60s cold boot + 15s `adb install`. Largest single optimization.
2. **Shard-split parallelism halves Maestro wall time** — `--shard-split 2` across 2 concurrent emulators. i7-6700 supports 2 instances at 2GB each without starving production containers.
3. **systemd slices prevent emulator from starving production** — `emulator.slice` caps CPU at 400% (4 of 8 threads), memory at 16G. No more manual babysitting.
4. **ADB port binding localhost-only is critical** — ADB has zero auth, active CVEs. Exposing 5555 on 0.0.0.0 is an immediate remote compromise vector. Docker must bind `127.0.0.1:5555:5555`.
5. **Moving instrumented tests to commonTest gives 10-60x faster feedback** — pure logic (parsing, serialization, ViewModel state machines) validated in seconds on JVM, not minutes on device.

---

## Tier 1: Pre-build Test Optimization

### Shared Test Stack

| Tool | Purpose | Dependency |
|------|---------|------------|
| `ktor-client-mock` | Mock HTTP responses in commonTest | `commonTest` dep |
| `mokkery` 2.x | Mock interfaces in commonTest (compiler plugin, cross-platform) | `commonTest` dep + compiler plugin |
| `turbine` | Test Flow emissions | `commonTest` dep |
| `kover` | Code coverage, 70-80% target on business logic | `:shared` plugin |

### MockEngine Pattern (Ktor)

```kotlin
// shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthApiTest.kt
val mockEngine = MockEngine { request ->
    when (request.url.encodedPath) {
        "/v1/auth/login" -> respond(
            """{"access_token":"test","refresh_token":"test","expires_in":3600}""",
            HttpStatusCode.OK,
            headersOf("Content-Type" to "application/json")
        )
        else -> respondError(HttpStatusCode.NotFound)
    }
}

val client = HttpClient(mockEngine) {
    install(ContentNegotiation) { json() }
}
```

### mokkery Pattern (Cross-platform Mocking)

```kotlin
// shared/src/commonTest/kotlin/ru/skatelab/shared/ble/Wt901CommanderTest.kt
@MokkeryProvider
interface TokenStorage {
    suspend fun getAccessToken(): String?
    suspend fun saveAccessToken(token: String)
}

class AuthRepositoryTest {
    val tokenStorage = mokkery<TokenStorage> {
        everySuspend { getAccessToken() } returns "test-token"
    }

    @Test
    fun `repository uses stored token`() = runTest {
        val repo = AuthRepository(tokenStorage, client)
        assertEquals("test-token", repo.getStoredToken())
        verifySuspend { tokenStorage.getAccessToken() wasCalled once }
    }
}
```

### turbine Pattern (ViewModel Flow Testing)

```kotlin
// shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthViewModelTest.kt
@Test
fun `login emits loading then success`() = runTest {
    val vm = AuthViewModel(fakeRepo)
    vm.uiState.test {
        awaitItem() // Initial state
        vm.login("user@test.ru", "pass")
        val loading = awaitItem()
        assertTrue(loading is UiState.Loading)
        val success = awaitItem()
        assertTrue(success is UiState.Success)
    }
}
```

**Setup:** `Dispatchers.Main.setMain(StandardTestDispatcher())` in test setup.

### BLE Testing Strategy

BLE code has `expect`/`actual` architecture. Test the shared layer by faking the `expect` interface:

```kotlin
// shared/src/commonTest/kotlin/ru/skatelab/shared/ble/Wt901ParserTest.kt
@Test
fun `parse acceleration packet from raw bytes`() {
    val raw = byteArrayOf(0x51, 0x00, 0x01, 0x02, ...)  // accel packet header
    val parsed = Wt901Parser.parseAccel(raw)
    assertEquals(9.8, parsed.x, 0.01)
}
```

Command parsers are pure functions (bytes in, structured data out). No Bluetooth hardware needed.

### Kover Configuration

```kotlin
// shared/build.gradle.kts
kover {
    reports {
        filters {
            excludes {
                classes(
                    "*_Generated*",          // Codegen
                    "*.di.*",                // DI modules
                    "*.ui.state.*",          // Sealed state classes
                    "*.platform.*",          // expect/actual platform stubs
                )
            }
        }
    }
}
```

Target: **70-80%** coverage on business logic. Exclude generated code, sealed state classes, DI modules, platform stubs.

### CI Gate: `:shared:allTests`

```yaml
# .github/workflows/mobile-test.yml — existing job, extend command
- name: Run shared tests
  run: ./gradlew :shared:allTests  # Runs commonTest on all targets (~seconds)
```

This validates both Android and iOS target logic in a single JVM run. If it fails, the APK build is skipped — saving 10-15 minutes of CI time per failure.

### Move Instrumented Tests to commonTest

| Currently instrumented | Move to commonTest? | Reason |
|------------------------|---------------------|--------|
| JSON encode/decode | Yes | Pure serialization, no Android context |
| API response parsing | Yes | MockEngine replaces real HTTP |
| ViewModel state transitions | Yes | turbine + StandardTestDispatcher |
| BLE command construction | Yes | Pure byte manipulation |
| BLE actual connection | No | Needs Android BluetoothManager |
| UI rendering | No | Needs Compose framework |

**ROI:** Single auth test in commonTest validates logic for both Android and iOS. Feedback in ~2s vs 10-15 min build+install.

---

## Tier 2: E2E Server Optimization

### Docker Compose (Emulator Container)

```yaml
# /opt/skatelab-e2e/docker-compose.yml
services:
  emulator:
    image: budtmo/docker-android:emulator_34.0
    container_name: skatelab-emulator
    devices:
      - /dev/kvm
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges=true
    ports:
      - "127.0.0.1:5555:5555"   # ADB — localhost ONLY
      - "127.0.0.1:5554:5554"  # Emulator console — localhost ONLY
    environment:
      EMULATOR_FLAGS: "-no-window -no-audio -no-boot-anim -gpu swiftshader_indirect -memory 2048 -netfast -accel on -partition-size 1024 -no-snapshot-save"
      DATAPARTITION: "1024m"
    tmpfs:
      - /data:size=2G          # Faster I/O for emulator data partition
    volumes:
      - emulator_data:/root/.android
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: 16G
        reservations:
          memory: 4G
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "adb shell getprop sys.boot_completed | grep -q 1"]
      interval: 10s
      timeout: 5s
      retries: 30
      start_period: 60s

volumes:
  emulator_data:
```

**Key decisions:**

| Decision | Choice | Reason |
|----------|--------|--------|
| Base image | `budtmo/docker-android` (15k stars) | API 34 support, maintained, headless-ready |
| GPU flag | `swiftshader_indirect` | Headless Maestro needs GPU. `-gpu off` is faster but risks app crash. |
| ADB bind | `127.0.0.1` only | ADB has zero authentication. Exposing on 0.0.0.0 = instant RCE. |
| tmpfs on /data | Yes | 2GB tmpfs eliminates disk I/O for emulator data partition |
| Resource limits | 4 CPUs, 16G | Leaves 4 threads + 46G for production containers |

### Emulator Flags Reference

```bash
/emulator/emulator @e2e_avd \
  -no-window \
  -no-audio \
  -no-boot-anim \
  -gpu swiftshader_indirect \
  -memory 2048 \
  -netfast \
  -accel on \
  -partition-size 1024 \
  -no-snapshot-save \    # Prevent test side-effects from corrupting snapshot
  -snapshot with_app_installed  # Restore from named snapshot (5-10s vs 30-60s cold boot)
```

### AVD Configuration

```ini
# ~/.android/avd/e2e_avd.avd/config.ini
hw.cpu.ncore=2
hw.ramSize=2048
hw.device.name=pixel_6
hw.lcd.density=420
hw.lcd.width=1080
hw.lcd.height=2400
disk.dataPartition.size=1024M
image.sysdir.1=system-images/android-34/google_apis/x86_64/
tag.id=google_apis
hw.gpu.mode=swiftshader_indirect
fastboot.forceColdBoot=no
fastboot.forceFastBoot=yes
```

Use smallest device profile that still matches real Pixel 6 resolution. Reduced rendering = faster tests.

### Named Snapshots (Biggest Time Saver)

```bash
# One-time: save snapshot with app pre-installed
adb shell avd snapshot save with_app_installed

# Per-run: restore snapshot (5-10s vs 30-60s cold boot + 15s adb install)
/emulator/emulator @e2e_avd -snapshot with_app_installed -no-snapshot-save

# -no-snapshot-save prevents test mutations from corrupting the clean snapshot
```

**Savings per run:**

| Step | Without Snapshot | With Snapshot | Saved |
|------|-----------------|---------------|-------|
| Boot | 30-60s | 5-10s | 25-50s |
| Install APK | 10-15s | 0s (pre-installed) | 10-15s |
| **Total** | **40-75s** | **5-10s** | **35-65s** |

For an APK update, re-install after snapshot restore (still faster than cold boot + install), then re-save the snapshot.

### Concurrent Emulators (2 Instances)

i7-6700 (4C/8T) supports 2 concurrent emulators. Each gets 2 vCPU + 2GB RAM.

```bash
# Emulator 1
/emulator/emulator @e2e_avd -port 5554 -snapshot with_app_installed -no-snapshot-save

# Emulator 2
/emulator/emulator @e2e_avd_2 -port 5556 -snapshot with_app_installed -no-snapshot-save
```

Port mapping: emulator-5554 (ports 5554/5555), emulator-5556 (ports 5556/5557).

**Resource budget:**

| Resource | Emulators (2x) | Production | Total Available | Headroom |
|----------|---------------|------------|-----------------|----------|
| CPU threads | 4 | 4 | 8 | 0 (80% utilized) |
| RAM | 4 GB | ~30 GB | 62 GB | 28 GB |
| Disk I/O | tmpfs (4 GB) | NVMe | NVMe | Sufficient |

---

## Maestro Parallel & Async Optimization

### Shard-split Parallelism

```bash
# Split flows across 2 emulators — halves wall time
maestro test \
  --device emulator-5554,emulator-5556 \
  --shard-split 2 \
  --format junit \
  --output /opt/skatelab-e2e/reports/report-$(date +%Y%m%d-%H%M%S).xml \
  .maestro/
```

**Built-in variables** (prevent artifact collisions):
- `MAESTRO_SHARD_INDEX` — 0 or 1, identifies which shard
- `MAESTRO_DEVICE_UDID` — unique per emulator

**Alternative: `--shard-all N`** runs ALL flows on ALL N devices (cross-validation, not time savings).

### Flow Tagging

```yaml
# .maestro/login.yaml
appId: ru.skatelab
tags:
  - smokeTest
  - auth
---
- launchApp
- assertVisible: "Войти"
- tapOn: "Войти"
```

```bash
# Run only smoke tests (faster feedback)
maestro test --includeTags smokeTest .maestro/

# Run everything except utility flows
maestro test --excludeTags util .maestro/
```

### Reporting

```bash
# JUnit XML (CI-parseable)
maestro test --format junit --output report.xml .maestro/

# HTML detailed (with screenshots, human-readable)
maestro test --format html-detailed --output report.html .maestro/

# Both at once
maestro test --format junit --output report.xml --format html-detailed --output report.html .maestro/
```

Screenshots captured automatically on failure. Video recording available via Maestro settings.

### Environment Variables

```bash
# Pass env vars to flows
maestro test -e API_URL=https://api.skatelab.ru -e TEST_USER=e2e@skatelab.ru .maestro/

# Or prefix with MAESTRO_ for auto-availability in flows
export MAESTRO_API_URL=https://api.skatelab.ru
export MAESTRO_TEST_USER=e2e@skatelab.ru
```

### Async Execution Wrapper

Maestro CLI is synchronous. For fire-and-forget (agent continues working while tests run):

```bash
#!/bin/bash
# /opt/skatelab-e2e/run-e2e-async.sh
REPORT_DIR="/opt/skatelab-e2e/reports"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="${REPORT_DIR}/report-${TIMESTAMP}.xml"

nohup maestro test \
  --device emulator-5554,emulator-5556 \
  --shard-split 2 \
  --format junit \
  --output "${REPORT_FILE}" \
  .maestro/ > "${REPORT_DIR}/maestro-${TIMESTAMP}.log" 2>&1 &

echo "${REPORT_FILE}" > "${REPORT_DIR}/latest-report-path.txt"
echo "Tests running. Report will be at: ${REPORT_FILE}"
echo "Poll with: test -f ${REPORT_FILE} && cat ${REPORT_FILE}"
```

Agent polls for JUnit XML existence:

```bash
# Check if tests are done
REPORT=$(cat /opt/skatelab-e2e/reports/latest-report-path.txt)
while [ ! -f "$REPORT" ]; do sleep 5; done
echo "Tests complete. Results:"
grep -c 'testcase.*failures="0"' "$REPORT" && echo "ALL PASSED" || echo "FAILURES DETECTED"
```

### Flaky Test Handling

Per-flow retry (not global):

```yaml
# .maestro/flaky-flow.yaml
appId: ru.skatelab
---
- retry:
    maxRetries: 3
    commands:
      - tapOn: "Refresh"
      - assertVisible: "Sessions"
```

No global `--retry` flag in Maestro yet. Wrap the runner script for whole-suite retry:

```bash
# /opt/skatelab-e2e/run-e2e.sh (retry wrapper)
MAX_RETRIES=2
ATTEMPT=0
while [ $ATTEMPT -le $MAX_RETRIES ]; do
    maestro test --shard-split 2 --format junit --output "$REPORT" .maestro/
    if grep -q 'failures="0"' "$REPORT"; then
        echo "All tests passed on attempt $((ATTEMPT+1))"
        exit 0
    fi
    ATTEMPT=$((ATTEMPT+1))
    echo "Attempt $ATTEMPT failed, retrying..."
    sleep 5
done
echo "Tests failed after $((MAX_RETRIES+1)) attempts"
exit 1
```

---

## systemd Slice + Service (Resource Isolation)

### Slice Definition

```ini
# /etc/systemd/system/emulator.slice
[Unit]
Description=Android Emulator Slice
DefaultDependencies=no
Before=slices.target

[Slice]
CPUQuota=400%          # 4 of 8 threads max
MemoryMax=16G           # Hard limit
MemoryHigh=12G          # Soft throttle
IOWeight=50             # Lower I/O priority than production
```

### Docker Service

```ini
# /etc/systemd/system/skatelab-emulator.service
[Unit]
Description=SkateLab Android Emulator (Docker)
After=docker.service
Requires=docker.service
Wants=network-online.target

[Service]
Slice=emulator.slice
Type=simple
ExecStartPre=-/usr/bin/docker compose -f /opt/skatelab-e2e/docker-compose.yml down
ExecStart=/usr/bin/docker compose -f /opt/skatelab-e2e/docker-compose.yml up --abort-on-container-exit
ExecStop=/usr/bin/docker compose -f /opt/skatelab-e2e/docker-compose.yml down
Restart=on-failure
RestartSec=10
WatchdogSec=60

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable skatelab-emulator.service
sudo systemctl start skatelab-emulator.service

# Verify slice assignment
systemctl status skatelab-emulator.service | grep Slice
# Should show: Slice: emulator.slice

# Check resource usage
systemctl show emulator.slice | grep -E 'CPUQuota|MemoryMax'
```

### Auto-start on Boot

The `WantedBy=multi-user.target` + `sudo systemctl enable` handles this. Emulator container starts automatically when server reboots, with Quick Boot resuming the AVD in <6s.

---

## Security Hardening

### ADB Access (Critical)

```yaml
# docker-compose.yml — CORRECT
ports:
  - "127.0.0.1:5555:5555"    # localhost only
  - "127.0.0.1:5554:5554"   # console localhost only

# WRONG — NEVER do this:
# ports:
#   - "5555:5555"            # 0.0.0.0 — remotely exploitable
```

ADB protocol has zero authentication. Active exploitation in the wild (CVE-2024-0044, etc.). Binding to 0.0.0.0 gives root shell to anyone who can reach port 5555.

### Docker Security

```yaml
services:
  emulator:
    devices:
      - /dev/kvm                        # KVM passthrough (narrow ioctl surface)
    cap_drop:
      - ALL                              # Drop all Linux capabilities
    security_opt:
      - no-new-privileges=true           # No SUID escalation
    # NEVER use --privileged
    read_only: true                       # Read-only root filesystem
    tmpfs:
      - /data:size=2G                    # Writable data via tmpfs
      - /tmp:size=512M                   # Temp files
```

**KVM ioctl attack surface:** Narrow. KVM ioctl subset (run, map memory) is well-scoped. Risk is acceptable given the container isolation + capability drop.

### SSH Access for Claude Code Agent

```bash
# Agent connects via SSH — use dedicated key, not password
ssh -i ~/.ssh/skatelab_e2e dedic "cd /opt/skatelab-e2e && ./run-e2e.sh --apk-path=/tmp/app-debug.apk"
```

Restrict the SSH key in `authorized_keys`:

```
command="/opt/skatelab-e2e/wrapper.sh",no-port-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... skatelab-e2e-agent
```

`wrapper.sh` validates allowed commands and rejects anything else.

### Firewall

```bash
# ADB ports must NOT be in any iptables INPUT allow rule
# If using ufw:
sudo ufw deny 5554
sudo ufw deny 5555
# They're already localhost-only in Docker, but defense in depth
```

---

## Monitoring & Observability

### No Native Prometheus Exporter

Android Emulator has no Prometheus exporter. Use a custom script writing to node_exporter textfile collector:

```bash
#!/bin/bash
# /opt/skatelab-e2e/metrics.sh — run via cron every 30s
METRIC_FILE="/var/lib/node_exporter/textfile_collector/emulator.prom"

# Is emulator running?
EMULATOR_UP=$(docker ps --filter name=skatelab-emulator --format '{{.Status}}' | grep -c Up)

# Boot status
BOOT_COMPLETE=$(docker exec skatelab-emulator adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || echo "0")

# CPU/Memory from cgroup (via systemd slice)
SLICE_MEM=$(systemctl show emulator.slice -p MemoryCurrent --value 2>/dev/null || echo "0")
SLICE_CPU=$(systemctl show emulator.slice -p CPUUsageNSec --value 2>/dev/null || echo "0")

cat > "${METRIC_FILE}.tmp" <<EOF
# HELP skatelab_emulator_up Whether the emulator container is running
# TYPE skatelab_emulator_up gauge
skatelab_emulator_up ${EMULATOR_UP}

# HELP skatelab_emulator_boot_complete Whether the Android VM has finished booting
# TYPE skatelab_emulator_boot_complete gauge
skatelab_emulator_boot_complete ${BOOT_COMPLETE}

# HELP skatelab_emulator_memory_bytes Current memory usage of emulator slice
# TYPE skatelab_emulator_memory_bytes gauge
skatelab_emulator_memory_bytes ${SLICE_MEM}

# HELP skatelab_emulator_cpu_ns_total CPU usage of emulator slice in nanoseconds
# TYPE skatelab_emulator_cpu_ns_total counter
skatelab_emulator_cpu_ns_total ${SLICE_CPU}
EOF

mv "${METRIC_FILE}.tmp" "${METRIC_FILE}"
```

```bash
# Cron job (every 30s)
* * * * * /opt/skatelab-e2e/metrics.sh
* * * * * sleep 30; /opt/skatelab-e2e/metrics.sh
```

### cAdvisor (Already Running)

cAdvisor monitors Docker containers by default. The emulator container will appear automatically with CPU, memory, network, and filesystem metrics. No additional config needed.

### Maestro Test Results Monitoring

```bash
# Parse JUnit XML for Grafana annotations or alerting
grep -o 'failures="[0-9]*"' /opt/skatelab-e2e/reports/latest-report-path.txt | head -1
```

---

## Cost Analysis

| Option | Cost | Notes |
|--------|------|-------|
| **Self-hosted (dedic)** | $0 incremental | Server already paid. Emulator + Maestro use existing CPU/RAM. |
| Firebase Test Lab | ~$250/mo | 100 runs/day at $5/device-hour. 1 device slot. |
| Maestro Cloud | ~$250/mo | Per device slot pricing. |
| AWS Device Farm | ~$170/mo | Pay-per-minute, less convenient. |

**Break-even:** At ~50 test runs/day, Firebase costs $250/mo. Self-hosted = $0. The dedic is already provisioned and underutilized (28 GB RAM headroom).

**Disk I/O:** Raw + preallocated vs QCOW2 is negligible on NVMe. QCOW2 is required for named snapshots. Use QCOW2.

---

## Delta from Original Spec

This section documents what this report adds, changes, or corrects relative to `docs/specs/2026-05-24-mobile-testing-automation-design.md`.

### Additions (Not in Original Spec)

| Item | Details |
|------|---------|
| **Named AVD snapshots** | `avd snapshot save with_app_installed` + `-snapshot` + `-no-snapshot-save`. Saves 35-65s per run. Not mentioned in original. |
| **Concurrent emulators (2x)** | Original spec describes single emulator. This report specifies 2 concurrent instances with shard-split. |
| **systemd slice** | `emulator.slice` with CPUQuota=400%, MemoryMax=16G. Not in original — critical for shared production server. |
| **Docker container** | Original spec describes bare-metal emulator. This report recommends Docker (`budtmo/docker-android`) for isolation on shared server. |
| **Docker security hardening** | `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `read_only: true`. Not in original. |
| **ADB localhost binding** | `127.0.0.1:5555:5555` not `5555:5555`. Critical security fix not in original. |
| **SSH key restriction** | `command=` in authorized_keys. Not in original. |
| **mokkery 2.x** | Cross-platform mocking for commonTest. Original only mentions ktor-client-mock and turbine. |
| **Kover config** | Coverage targets and exclusion filters. Not in original. |
| **Maestro shard-split** | `--shard-split 2` across 2 emulators. Original describes single-device Maestro. |
| **Maestro tagging** | `--includeTags` / `--excludeTags`. Not in original. |
| **Maestro async wrapper** | `nohup` + poll pattern for fire-and-forget. Not in original. |
| **Flaky test retry** | Per-flow `retry: maxRetries: 3` + runner script retry wrapper. Not in original. |
| **Prometheus metrics** | Custom script to node_exporter textfile collector. Not in original. |
| **tmpfs for /data** | 2GB tmpfs mount for emulator data partition. Not in original. |
| **AVD config.ini** | Specific `hw.cpu.ncore`, `hw.ramSize`, density values. Original only says "API 34, x86_64, 4GB RAM". |
| **Move instrumented to commonTest** | Explicit classification of what moves vs stays. Original only says "extend commonTest". |

### Changes (Modifies Original Spec)

| Item | Original | Updated | Reason |
|------|----------|---------|--------|
| **Emulator RAM** | 4GB | 2GB | 2GB sufficient for E2E. 2x emulators at 2GB = 4GB total, leaves headroom. |
| **Docker vs bare metal** | Bare-metal scripts | Docker container | Isolation critical on shared production server. ~5-8% I/O overhead acceptable. |
| **GPU flag** | `-gpu swiftshader_indirect` | Same, but explicitly warn `-gpu off` risks crash | Original lists flag without justification. |
| **Quick Boot** | Not mentioned | Default since emulator 27.x, <6s resume | Should be assumed, not configured. |
| **Phase 2 scope** | "Install emulator + Maestro" | Includes Docker, systemd slice, snapshots, shard-split | Original underestimates Phase 2 infrastructure. |

---

## Prioritized Implementation Order

Ordered by impact-per-effort. Each step is independently valuable.

| # | Task | Impact | Effort | Dependency |
|---|------|--------|--------|------------|
| 1 | **Move pure-logic tests to commonTest** | 10-60x faster feedback, catches bugs before build | 1-2 days | None — CI already runs `:shared:testDebugUnitTest` |
| 2 | **Add mokkery + MockEngine + turbine** | Enables proper mocking/flow testing in commonTest | 0.5 day | #1 |
| 3 | **Configure Kover** | Coverage visibility, 70-80% target | 0.5 day | #1 |
| 4 | **Set up Docker emulator on dedic** | Enables E2E testing without physical device | 0.5 day | SSH access to dedic |
| 5 | **systemd slice + service** | Prevents emulator from starving production | 0.5 day | #4 |
| 6 | **Save named AVD snapshot** | 35-65s saved per E2E run | 15 min | #4 |
| 7 | **ADB localhost binding + Docker hardening** | Blocks remote ADB exploitation | 15 min | #4 |
| 8 | **Write first 3-5 Maestro flows** | Basic E2E coverage (login, sessions, record, upload) | 1 day | #4 |
| 9 | **Shard-split across 2 emulators** | Halves Maestro wall time | 0.5 day | #4, #6 |
| 10 | **Prometheus metrics script** | Visibility into emulator health | 0.5 day | #4, #5 |
| 11 | **Maestro tagging + smoke test subset** | Faster feedback loop for smoke tests | 0.5 day | #8 |
| 12 | **Async wrapper + retry logic** | Fire-and-forget + flaky resilience | 0.5 day | #8 |
| 13 | **SSH key restriction** | Agent can only run allowed commands | 15 min | SSH access |
| 14 | **Expand Maestro flows** | Full coverage (calibration, export, settings) | 2 days | #8 |
| 15 | **API version matrix (API 30 + 34)** | Broader compatibility testing | 1 day | #9, extra AVD |

**Total estimated effort: ~8-10 days** for full implementation (items 1-13). Items 14-15 are expansion and can be done iteratively.

### Critical Path

Items 1-3 (commonTest) have zero infrastructure dependency and give the highest ROI. Start there.

Items 4-7 (server setup) unlock everything else. A single focused session on the dedic gets Docker + systemd + snapshots + security done.

Items 8-12 (Maestro) build on the server and provide the E2E safety net.
