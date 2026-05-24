# Mobile Testing Automation Design

**Goal:** Eliminate manual testing from the mobile app development loop by automating pre-build shared module tests and E2E UI tests via Maestro on a dedicated server.

**Architecture:** Two-tier testing pipeline — Tier 1 runs shared module unit/integration tests before APK build (CI, ~2 min), Tier 2 runs Maestro E2E flows on an Android emulator hosted on the production dedicated server (i7-6700, 8 CPU, 62 GB RAM, KVM enabled). Claude Code agent orchestrates E2E via SSH.

**Tech Stack:** Kotlin Test + ktor-client-mock + turbine (shared tests), Maestro CLI v0.14.5+ (E2E), Android Emulator with KVM (dedic), adb (install/control)

---

## Problem Statement

Current mobile testing workflow:

1. CI builds APK (~10-15 min)
2. Developer physically connects Android phone via USB
3. `adb install` APK
4. Manual tap-through testing
5. Read logs, UI dumps for diagnostics
6. Report issues to agent or fix manually

**Bottlenecks:**
- **Phone tethered to dev machine** — developer loses their phone
- **No version matrix** — only one Android API version tested
- **Human in the loop** — manual UI testing is the primary bottleneck
- **Post-build only** — auth/API/BLE logic tested after full APK build, wasting CI time on preventable failures

## Design

### Tier 1: Pre-build Shared Module Tests

Run in CI before APK build. Catch auth, API, serialization, BLE logic errors without building the app.

**Test areas:**

| Area | Tests | Location | Tools |
|------|-------|----------|-------|
| Auth | login, register, refresh, token storage | `shared/src/commonTest/kotlin/ru/skatelab/shared/auth/` | ktor-client-mock, turbine |
| Sessions API | CRUD, list, get, create | `shared/src/commonTest/kotlin/ru/skatelab/shared/api/` | ktor-client-mock |
| Upload API | multipart upload, progress tracking | `shared/src/commonTest/kotlin/ru/skatelab/shared/api/` | ktor-client-mock |
| BLE/IMU | Wt901Commander, Wt901Parser, ImuCollector | `shared/src/commonTest/kotlin/ru/skatelab/shared/ble/` | kotlin.test |
| Serialization | JSON encode/decode for all models | `shared/src/commonTest/kotlin/ru/skatelab/shared/models/` | kotlin.test |

**Existing tests (extend, don't replace):**
- `AuthApiTest.kt`, `ProcessApiTest.kt` — already in commonTest
- `AuthRepositoryTest.kt`, `AuthViewModelTest.kt` — already in commonTest
- `SerializationTest.kt` — already in commonTest

**CI integration:** Already runs via `mobile-test.yml` → `shared-test` job (`./gradlew :shared:testDebugUnitTest`). New tests auto-included.

**Principle:** Mock HTTP layer (Ktor client mock). Test pure repository/ViewModel logic. BLE/IMU tests cover parsing and command logic without real Bluetooth.

### Tier 2: Maestro E2E on Dedicated Server

**Server:** 176.9.0.156 (i7-6700, 8 CPU, 62 GB RAM, KVM enabled)

**Infrastructure:**

```
Dedic (176.9.0.156)
├── Android Emulator (KVM, headless)
│   - AVD: API 34, x86_64, 4GB RAM
│   - Flags: -no-window -no-audio -gpu swiftshader_indirect
│   - adb headless
├── Maestro CLI (v0.14.5+)
│   - Installed via: curl -Ls "https://get.maestro.mobile.dev" | bash
│   - Runs flow.yaml tests against emulator
└── Scripts
    ├── /opt/skatelab-e2e/setup-emulator.sh  # One-time: create AVD, install deps
    ├── /opt/skatelab-e2e/run-e2e.sh         # Per-run: start emulator, install APK, run Maestro
    └── /opt/skatelab-e2e/flows/              # Maestro YAML test files (symlinked from repo)
```

**E2E test structure in repo:**

```
mobile/e2e/
├── flows/
│   ├── login.yaml           # Auth flow: launch → tap login → enter creds → assert sessions screen
│   ├── session-list.yaml    # Session list: launch (logged in) → assert session items
│   ├── recording.yaml       # Recording: launch → start recording → assert timer
│   └── upload.yaml          # Upload: select session → upload → assert progress
├── run-e2e.sh               # Orchestration script
└── setup-emulator.sh        # One-time emulator setup
```

**Maestro flow example:**

```yaml
appId: ru.skatelab
---
- launchApp
- assertVisible: "Войти"
- tapOn: "Войти"
- inputText: "test@skatelab.ru"
- tapOn: "Продолжить"
- assertVisible: "Сессии"
```

**run-e2e.sh workflow:**

1. Start Android emulator headless (KVM)
2. Wait for boot (`adb wait-for-device`)
3. Download APK from GitHub artifact (`gh run download`) or accept local path
4. `adb install` APK
5. `maestro test mobile/e2e/flows/` — runs all flows
6. Output: JUnit XML report + screenshots
7. Stop emulator

**Claude Code agent integration:**

```
Agent in Claude Code → SSH to dedic → run-e2e.sh
                                        ↓
                                   Emulator + Maestro
                                        ↓
                                   Report (pass/fail + screenshots)
                                        ↓
                                   Agent reads report → fix or revert
```

Manual invocation also works:
```bash
ssh dedic "cd /opt/skatelab-e2e && ./run-e2e.sh --apk-path=/tmp/app-debug.apk"
```

**Why not self-hosted runner:** Adds security surface, maintenance burden, concurrent job management. SSH + script is simpler for a single developer.

### Platform Scope

**Android only** for now. Maestro has a known issue with iOS + Compose Multiplatform (#1549) — accessibility tree not exposed, elements not detectable. iOS E2E would require XCUITest + Mac, deferred.

### Phased Rollout

**Phase 1 (days): Pre-build shared tests**
- Extend `commonTest` with auth, sessions, upload, BLE/IMU tests
- No infrastructure changes — runs in existing CI
- Immediate value: catch logic bugs before build

**Phase 2 (~1 week): Maestro setup on dedic**
- Install Android emulator + Maestro CLI on dedic (176.9.0.156)
- Write setup scripts (`setup-emulator.sh`, `run-e2e.sh`)
- Write first 3-5 Maestro flow.yaml files (login, session list, recording start, upload)
- Verify end-to-end: SSH → run-e2e.sh → report

**Phase 3 (later): Expand coverage**
- More Maestro flows (calibration, export, settings)
- API version matrix (API 30, 34) on emulator
- Automate via Claude Code agent (agent reads E2E report, auto-fixes)

## Key Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| E2E tool | Maestro | Mature (10K+ stars), YAML-based, low flakiness, Compose Android support |
| E2E host | Dedicated server | Free, always available, KVM enabled, 62GB RAM |
| CI integration | SSH + script, not self-hosted runner | Simpler for single developer, less security surface |
| iOS E2E | Deferred | Compose Multiplatform accessibility issue (#1549) |
| Test priority | Pre-build first | Fastest ROI — catches bugs without build time |
| Android API version | API 34 only initially | Covers modern devices, expand later |
