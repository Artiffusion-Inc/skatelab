# KMP Mobile CI Restructure

**Date:** 2026-05-24
**Status:** Draft
**Scope:** `mobile.yml` workflow → restructured entry + reusable workflows + composite actions
**Research:** 5-agent deep review (Gradle cache, GH Actions optimization, KMP/iOS, cost/runners, async patterns)

## Problem

Current `mobile.yml` is monolithic (5+ jobs, ~200 lines). Critical issues:

1. **Concurrency control exists** (already on master) — but no merge queue integration
2. **Configuration cache silently discarded** — `setup-gradle@v4` without `cache-encryption-key` = config-cache state never saved in CI (source: [No3x blog](https://no3x.de/blog/github-gradle-action-saving-configuration-cache-state))
3. **No iOS tests** — only `ios-compile` exists on `macos-14`
4. **`android-build-debug` serialized after `android-test`** — no logical dependency, wastes 5-15min on critical path
5. **CocoaPods in maintenance mode** — JetBrains KT-53877: EOL Q2 2026, migrate to SPM
6. **`generateDummyFramework` obsolete** — workaround for Kotlin <1.5.20; use `embedAndSignAppleFrameworkForXcode` instead
7. **No `timeout-minutes`** — runaway jobs bill indefinitely
8. **GitHub Actions billing exhausted** — private repo = 2000 min/mo free tier
9. **All Android jobs on same 2vcpu ARM runner** — heavier jobs (test, build) could use 4vcpu

Best practices from [AKJAW/kotlin-multiplatform-github-actions](https://github.com/AKJAW/kotlin-multiplatform-github-actions):
- Entry workflow + reusable workflows via `workflow_call`
- Composite actions for setup duplication elimination
- Label-based conditional builds
- Concurrency: cancel in-progress on feature branches

## Architecture

```
.github/
├── workflows/
│   ├── mobile-ci.yml            ← entry point (triggers, labels, concurrency, merge queue)
│   ├── mobile-build.yml         ← reusable: Android APK + iOS framework
│   ├── mobile-test.yml          ← reusable: shared + Android + iOS tests + coverage
│   ├── mobile-lint.yml          ← reusable: ktlint
│   └── mobile-nightly.yml       ← scheduled: cache warm + full CI on master
└── actions/
    └── setup-java-gradle/       ← composite: JDK 17 + setup-gradle@v6 + .konan cache + wrapper validation
        └── action.yml
```

**Key change from v1 spec:** Removed `setup-ios` composite action. CocoaPods + `generateDummyFramework` are obsolete. iOS jobs use `setup-java-gradle` + explicit `.konan` cache only.

## Workflow Details

### mobile-ci.yml (entry point)

**Triggers:**
```yaml
on:
  push:
    branches: [master]
    paths: [mobile/**, .github/workflows/mobile*.yml, .github/actions/setup-java-gradle/**]
  pull_request:
    branches: [master]
    paths: [same]
  merge_group:                    # ← NEW: merge queue support
  workflow_dispatch:
    inputs:
      run-all:
        description: 'Run all jobs regardless of changed files'
        default: false
        type: boolean
```

**Concurrency:**
```yaml
concurrency:
  group: mobile-ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}
```

**Changes job:** Detect changed modules via `dorny/paths-filter@v3`.

YAML anchors for shared filter:
```yaml
filters: |
  shared: &shared
    - 'mobile/shared/**'
    - 'mobile/build-logic/**'
    - 'mobile/gradle/**'
    - 'mobile/build.gradle.kts'
    - 'mobile/settings.gradle.kts'
    - 'mobile/gradle.properties'
  android:
    - 'mobile/androidApp/**'
    - *shared
  ios:
    - 'mobile/iosApp/**'
    - *shared
  build-logic:
    - 'mobile/build-logic/**'
    - 'mobile/gradle/**'
```

Outputs: `shouldRunShared`, `shouldRunAndroid`, `shouldRunIos`, `shouldRunBuildLogic`

**Downstream jobs:** Call reusable workflows conditionally.

**Build parallel to tests:** `android-build` no longer depends on `android-test`. Both start after `changes`.

**Summary gate job:**
```yaml
mobile-ci-passed:
  name: Mobile CI Passed
  needs: [changes, android-lint, shared-test, android-test, ios-test, android-build, ios-build]
  if: always()
  runs-on: blacksmith-2vcpu-ubuntu-2404
  timeout-minutes: 2
  steps:
    - name: Evaluate results
      env:
        NEEDS_JSON: ${{ toJson(needs) }}
      run: |
        python3 << 'PYEOF'
        import json, sys
        needs = json.loads(json.loads(os.environ["NEEDS_JSON"]))
        for name, data in needs.items():
            result = data.get("result", "unknown")
            if result in ("failure", "cancelled"):
                print(f"::error::{name} failed: {result}")
                sys.exit(1)
        PYEOF
```

Branch protection requires only: `Mobile CI Passed` (single gate check).

### Tiered CI: PR vs Merge Queue

| Tier | Trigger | Runs | Skips |
|------|---------|------|-------|
| Fast (PR) | `pull_request` | lint, shared-test, android-test | ios-test, android-build |
| Full (merge queue) | `merge_group` | everything | nothing |

```yaml
ios-test:
  if: ${{ inputs.run-all || needs.changes.outputs.ios == 'true' || github.event_name == 'merge_group' }}

android-build:
  if: ${{ inputs.run-all || needs.changes.outputs.android == 'true' || github.event_name == 'merge_group' }}
```

Label `run-ios-tests` on PR opts into iOS tests before merge queue.

### mobile-build.yml (reusable)

`on: workflow_call` with inputs: `shouldRunAndroid`, `shouldRunIos`

**Jobs:**
- `android-build` (blacksmith-4vcpu-ubuntu-2404-arm): `./gradlew :androidApp:assembleDebug` → upload APK (retention: 7 days)
- `ios-build` (macos-14): `setup-java-gradle` → `./gradlew :shared:linkDebugFrameworkIosSimulatorArm64` (simulator only for CI speed)

### mobile-test.yml (reusable)

`on: workflow_call` with inputs: `shouldRunShared`, `shouldRunAndroid`, `shouldRunIos`

**Jobs:**
- `shared-test` (blacksmith-4vcpu-ubuntu-2404-arm): `./gradlew :shared:allTests` → Kover coverage → Codecov
- `android-test` (blacksmith-4vcpu-ubuntu-2404-arm): `./gradlew :androidApp:testDebugUnitTest` → Kover coverage → Codecov
- `ios-test` (macos-14): `./gradlew :shared:iosSimulatorArm64Test` → junit xml upload

All use `setup-java-gradle` composite action.

### mobile-lint.yml (reusable)

`on: workflow_call` with input: `shouldRunAndroid`

**Jobs:**
- `android-lint` (blacksmith-2vcpu-ubuntu-2404-arm): `./gradlew :androidApp:ktlintCheck`

### mobile-nightly.yml

Scheduled cache warm + full CI validation on master:
```yaml
on:
  schedule:
    - cron: "3 4 * * *"   # 04:03 UTC daily
  push:
    branches: [master]
    paths: [mobile/gradle/**, mobile/build-logic/**]

jobs:
  gradle-cache-warm:
    runs-on: blacksmith-4vcpu-ubuntu-2404-arm
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - run: cd mobile && ./gradlew :shared:dependencies :androidApp:dependencies --configuration-cache

  konan-cache-warm:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - run: cd mobile && ./gradlew :shared:compileKotlinIosSimulatorArm64 --configuration-cache

  full-ci:
    needs: [gradle-cache-warm, konan-cache-warm]
    uses: ./.github/workflows/mobile-ci.yml
    with:
      run-all: true
    secrets: inherit
```

## Composite Actions

### setup-java-gradle (replaces both old setup-android and setup-ios)

```yaml
name: Setup Java + Gradle
description: JDK 17 + Gradle cache + Kotlin/Native cache + wrapper validation + sticky disks
inputs:
  java-version:
    default: '17'

runs:
  using: composite
  steps:
    # Supply-chain security
    - uses: gradle/actions/wrapper-validation@v3

    - uses: actions/setup-java@v5
      with:
        distribution: temurin
        java-version: ${{ inputs.java-version }}

    # setup-gradle@v6 with OSS caching + config-cache encryption
    - uses: gradle/actions/setup-gradle@v6
      with:
        cache-provider: basic
        cache-encryption-key: ${{ secrets.GRADLE_CACHE_ENCRYPTION_KEY }}
        dependency-graph: generate-and-submit

    # Sticky disk: ~/.gradle (persistent across jobs, 3s access vs 15s cache download)
    - name: Mount Gradle home sticky disk
      uses: useblacksmith/stickydisk@v1
      with:
        key: ${{ github.repository }}-gradle-home
        path: ~/.gradle

    # Sticky disk: ~/.konan (Kotlin/Native compiler, ~500MB)
    - name: Mount Kotlin/Native sticky disk
      uses: useblacksmith/stickydisk@v1
      with:
        key: ${{ github.repository }}-konan
        path: ~/.konan

    - name: Make gradlew executable
      shell: bash
      run: chmod +x mobile/gradlew
```

**Secret required:** `GRADLE_CACHE_ENCRYPTION_KEY` — generate via `openssl rand -base64 16`, save as repo secret.

**Why Sticky Disks instead of `actions/cache`:**
- `actions/cache`: 90 MB/s (GitHub) / 400 MB/s (Blacksmith colo) → ~15s for 6GB
- `useblacksmith/stickydisk`: hot-loaded block device, ext4 mount → **~3 seconds** for any size
- Gradle home (`~/.gradle`) easily 5-10GB with caches + wrappers + daemon
- `.konan` is ~500MB for Kotlin/Native compiler
- Sticky disks persist across runs without re-download — near-instant access
- Cost: $0.50/GB/mo — for ~15GB total = ~$7.50/mo (negligible vs runner minutes saved)

**Why this replaces both old actions:**
- `setup-ios` composite removed: CocoaPods deprecated (KT-53877), `generateDummyFramework` obsolete (Kotlin 1.5.20+)
- iOS jobs just need JDK + Gradle + .konan — same as Android
- No CocoaPods setup needed for `iosSimulatorArm64Test` (Gradle-native task)

### Sticky Disk for Android build directory

For the `android-build` job specifically, the Gradle project build cache (`mobile/.gradle`) is also large. Add a project-level sticky disk:

```yaml
# In android-build job only
- name: Mount Android project build cache
  uses: useblacksmith/stickydisk@v1
  with:
    key: ${{ github.repository }}-android-build-cache
    path: mobile/.gradle
```

This persists `mobile/.gradle/caches/transforms-*`, `build-cache/`, and other per-project artifacts between runs.

## Caching Strategy

### 3-Layer Caching (fastest → largest)

| Layer | Mechanism | Access time | Size | Cost |
|---|---|---|---|---|
| 1. Gradle build cache | `setup-gradle@v6` (basic) | ~15s (Blacksmith colo) | 1-3 GB | Free (included) |
| 2. Configuration cache | `setup-gradle@v6` + encryption key | ~15s | 100-500 MB | Free (included) |
| 3. Sticky disks | `useblacksmith/stickydisk@v1` | **~3s** | 10-15 GB total | ~$7.50/mo |

### What goes where

| Cache target | Layer | Why |
|---|---|---|
| `~/.gradle/caches` | Sticky disk | Gradle dependency cache, 5-10GB, slow to repopulate |
| `~/.gradle/wrapper` | Sticky disk | Wrapper distributions, ~200MB |
| `~/.konan` | Sticky disk | Kotlin/Native compiler (~500MB) + klib caches |
| `mobile/.gradle` | Sticky disk (build job only) | Project build cache, transforms, 1-5GB |
| Gradle build cache | `setup-gradle@v6` | Task outputs, incremental compilation |
| Configuration cache | `setup-gradle@v6` + encryption key | Config phase skip — **critical:** without key = no-op in CI |
| Gradle wrapper | `wrapper-validation@v3` | Checksum verification (supply-chain security) |

### Git checkout caching

Use `useblacksmith/checkout` (drop-in for `actions/checkout`) for repos where clone is slow:
```yaml
- uses: useblacksmith/checkout@v1  # instead of actions/checkout@v6
```
Keeps a persistent git mirror on sticky disk — incremental fetch instead of full clone. Worth it for repos >1GB.

**gradle.properties tuning:**
```properties
org.gradle.configuration-cache=true
org.gradle.parallel=true
org.gradle.caching=true
kotlin.incremental.native=true          # ← NEW: experimental incremental klib
```

**JVM heap tuning per runner type:**
```yaml
# In CI env (via GRADLE_OPTS or job env)
env:
  GRADLE_OPTS: "-Dorg.gradle.workers.max=2 -Dorg.gradle.jvmargs=-Xmx2g"
```

Private repos: 2 vCPU / 8GB → `workers.max=2`, `Xmx2g`. Public repos: 4 vCPU / 16GB → `workers.max=3`, `Xmx3g`.

## Runner Strategy

| Job | Runner | Rationale |
|---|---|---|
| `changes` | blacksmith-2vcpu-ubuntu-2404-arm | Lightweight, <30s |
| `android-lint` | blacksmith-2vcpu-ubuntu-2404-arm | CPU-light |
| `shared-test` | blacksmith-4vcpu-ubuntu-2404-arm | Gradle tests need RAM |
| `android-test` | blacksmith-4vcpu-ubuntu-2404-arm | Unit tests need RAM |
| `android-build` | blacksmith-4vcpu-ubuntu-2404-arm | APK assembly needs RAM |
| `ios-test` | macos-14 | Apple Silicon M1, native ARM64 simulator |
| `ios-build` | macos-14 | Same — Apple Silicon for native simulator |
| `mobile-ci-passed` | blacksmith-2vcpu-ubuntu-2404-arm | Summary gate, <30s |

**Already on Blacksmith ARM runners** (matching existing `ci-reusable.yml` config). iOS uses `macos-14` (Apple Silicon M1).

**Blacksmith runners:** Already onboarded for main CI. 33% cheaper per minute + faster hardware. Mobile CI should use them too.

## iOS Test Coverage

- Runner: `macos-14` (Apple Silicon M1)
- Command: `./gradlew :shared:iosSimulatorArm64Test`
- No CocoaPods, no `generateDummyFramework` — Gradle-native task
- Test results: junit xml → `actions/upload-artifact` (retention: 14 days)
- Coverage: not in v1 (Kover doesn't support iOS; xcresult is separate effort)

## Cost Savings

| Technique | Estimated saving |
|---|---|
| Sticky disks (~/.gradle, ~/.konan, mobile/.gradle) | **~60-70% faster builds** (3s access vs 15-66s cache download) |
| Config-cache encryption key | ~30% faster (config phase skipped on cache hit) |
| Concurrency cancel-in-progress (already present) | ~30% fewer runs on busy PRs |
| Gradle build cache (setup-gradle@v6) | ~40% faster incremental builds |
| Label-based skip + tiered CI | Skip iOS builds on Android-only PRs (~50% macOS minutes) |
| Build parallel to test | -5 to -15min from critical path |
| 4vcpu runners for heavy jobs (vs 2vcpu) | Faster Gradle builds on test/build |
| Path filters (already present) | Skip entire mobile CI on backend-only PRs |

**Estimated monthly cost (50 PRs/mo):**

| Scenario | Cost |
|---|---|
| Current (ubuntu-latest, no cache, no parallelism) | ~$144/mo |
| Optimized (Blacksmith, cache, parallel build, tiered CI) | ~$52/mo |
| **Savings** | **~64%** |

## Async & Event-Driven Patterns

### Tiered CI (PR vs Merge Queue)

Already covered above. Fast checks on PR, full checks only in merge queue.

### Label-Triggered iOS Tests

PRs can opt into iOS tests before merge queue:
```yaml
ios-test:
  if: ${{ inputs.run-all || needs.changes.outputs.ios == 'true' || github.event_name == 'merge_group' || contains(github.event.pull_request.labels.*.name, 'run-ios-tests') }}
```

### Cache Warming

Nightly scheduled job (`mobile-nightly.yml`) populates Gradle + Konan caches so PRs get cache hits.

### Future: `workflow_run` Chains

For post-merge integration testing, `workflow_run` can trigger mobile CI after backend CI succeeds. Not in v1.

### Future: Test Sharding

JUnit 5 sharding via matrix strategy for large test suites. Not in v1.

### Future: Comment-Triggered Commands

`/run-ios` bot comment triggers specific iOS jobs via `issue_comment` + `slash-command-dispatch`. Not in v1.

## Supply-Chain Security

| Measure | Implementation |
|---|---|
| Wrapper validation | `gradle/actions/wrapper-validation@v3` in composite action |
| Dependency graph | `setup-gradle@v6` with `dependency-graph: generate-and-submit` |
| Dependency verification (future) | `verification-metadata.xml` + `--dependency-verification lenient` → `strict` |

## Migration Plan

1. Add `GRADLE_CACHE_ENCRYPTION_KEY` secret to repo
2. Create `setup-java-gradle` composite action
3. Create `mobile-build.yml`, `mobile-test.yml`, `mobile-lint.yml` reusable workflows
4. Create `mobile-ci.yml` entry point + `mobile-nightly.yml`
5. Test on feature branch
6. Delete `mobile.yml` (mobile-ci.yml fully replaces it)
7. Update branch protection: require `Mobile CI Passed` as sole status check
8. Enable merge queue on `master`

## Out of Scope

- Release signing / Play Store / TestFlight deployment
- Backend / frontend CI changes
- Self-hosted runners (VPS or Mac Mini)
- Android instrumented tests (Firebase Test Lab / GMD)
- Dependency verification (`verification-metadata.xml`)
- Test sharding
- `workflow_run` chains
- Xcode Cloud integration

## Sources

- [No3x: Configuration cache encryption key](https://no3x.de/blog/github-gradle-action-saving-configuration-cache-state)
- [Gradle blog: v6 changes](https://blog.gradle.org/github-actions-for-gradle-v6)
- [Gradle blog: Choice and Clarity (caching licensing)](https://blog.gradle.org/choice-clarity-future-caching-gradle-actions)
- [JetBrains KT-53877: CocoaPods maintenance mode](https://youtrack.jetbrains.com/issue/KT-53877)
- [Kotlin/Native compilation tips](https://kotlinlang.org/docs/native-improving-compilation-time.html)
- [Touchlab: Build only what you need](https://touchlab.co/touchlab-build-only-what-you-need)
- [Andreas Fuchs: Merge queue gatherer pattern](https://boinkor.net/2023/11/neat-github-actions-patterns-for-github-merge-queues)
- [GitHub: macOS runner pricing changes](https://github.blog/changelog/2025-12-16)
- [GitHub Actions runners hardware](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Gradle dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [AKJAW/kotlin-multiplatform-github-actions](https://github.com/AKJAW/kotlin-multiplatform-github-actions)