# KMP Mobile CI Restructure

**Date:** 2026-05-24
**Status:** Draft
**Scope:** `mobile.yml` workflow → restructured entry + reusable workflows + composite actions
**Research:** 5-agent deep review (Gradle cache, GH Actions optimization, KMP/iOS, cost/runners, async patterns)

## Problem

Current `mobile.yml` is monolithic (5+ jobs, ~200 lines). Critical issues:

1. **No concurrency control** — redundant runs on same PR
2. **Configuration cache silently discarded** — `setup-gradle@v4` without `cache-encryption-key` = config-cache state never saved in CI (source: [No3x blog](https://no3x.de/blog/github-gradle-action-saving-configuration-cache-state))
3. **No Gradle caching** — cold start every run
4. **No iOS tests** — only `ios-compile` exists
5. **`android-build-debug` serialized after `android-test`** — no logical dependency, wastes 5-15min on critical path
6. **`macos-13` runner** — Intel x86_64, 3x slower than M1 (`macos-14`)
7. **CocoaPods in maintenance mode** — JetBrains KT-53877: EOL Q2 2026, migrate to SPM
8. **`generateDummyFramework` obsolete** — workaround for Kotlin <1.5.20; use `embedAndSignAppleFrameworkForXcode` instead
9. **No `timeout-minutes`** — runaway jobs bill indefinitely
10. **GitHub Actions billing exhausted** — private repo = 2000 min/mo free tier

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
  needs: [changes, lint, shared-test, android-test, ios-test, android-build, ios-build]
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
- `android-build` (blacksmith-4vcpu-ubuntu-2404): `./gradlew :androidApp:assembleDebug` → upload APK (retention: 7 days)
- `ios-compile` (macos-14): `setup-java-gradle` → `./gradlew :shared:linkDebugFrameworkIosSimulatorArm64` (simulator only for CI speed)

### mobile-test.yml (reusable)

`on: workflow_call` with inputs: `shouldRunShared`, `shouldRunAndroid`, `shouldRunIos`

**Jobs:**
- `shared-test` (blacksmith-4vcpu-ubuntu-2404): `./gradlew :shared:allTests` → Kover coverage → Codecov
- `android-test` (blacksmith-4vcpu-ubuntu-2404): `./gradlew :androidApp:testDebugUnitTest` → Kover coverage → Codecov
- `ios-test` (macos-14): `./gradlew :shared:iosSimulatorArm64Test` → junit xml upload

All use `setup-java-gradle` composite action.

### mobile-lint.yml (reusable)

`on: workflow_call` with input: `shouldRunAndroid`

**Jobs:**
- `android-lint` (blacksmith-2vcpu-ubuntu-2404): `./gradlew :androidApp:ktlintCheck`

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
    runs-on: blacksmith-4vcpu-ubuntu-2404
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
description: JDK 17 + Gradle cache + Kotlin/Native cache + wrapper validation
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

    # Explicit Kotlin/Native cache (not covered by setup-gradle basic)
    - name: Cache Kotlin/Native .konan
      uses: actions/cache@v4
      with:
        path: ~/.konan
        key: konan-${{ runner.os }}-${{ hashFiles('mobile/gradle/libs.versions.toml', 'mobile/gradle/wrapper/gradle-wrapper.properties') }}
        restore-keys: |
          konan-${{ runner.os }}-

    - name: Make gradlew executable
      shell: bash
      run: chmod +x mobile/gradlew
```

**Secret required:** `GRADLE_CACHE_ENCRYPTION_KEY` — generate via `openssl rand -base64 16`, save as repo secret.

**Why this replaces both old actions:**
- `setup-ios` composite removed: CocoaPods deprecated (KT-53877), `generateDummyFramework` obsolete (Kotlin 1.5.20+)
- iOS jobs just need JDK + Gradle + .konan cache — same as Android
- No CocoaPods setup needed for `iosSimulatorArm64Test` (Gradle-native task)

## Caching Strategy

| Cache target | Mechanism | Key basis | Notes |
|---|---|---|---|
| Gradle build cache | `setup-gradle@v6` (basic) | auto by action | Replaces manual `actions/cache` for Gradle |
| Configuration cache | `setup-gradle@v6` + encryption key | auto | **Critical:** without encryption key, config-cache state silently discarded |
| Kotlin/Native `.konan` | explicit `actions/cache@v4` | OS + toml + wrapper props | Compiler download (~500MB) + unpack (~24s) avoided |
| Gradle wrapper | `wrapper-validation@v3` | checksum verification | Supply-chain security |

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
| `changes` | blacksmith-2vcpu-ubuntu-2404 | Lightweight, <30s |
| `android-lint` | blacksmith-2vcpu-ubuntu-2404 | CPU-light |
| `shared-test` | blacksmith-4vcpu-ubuntu-2404 | Gradle tests need RAM |
| `android-test` | blacksmith-4vcpu-ubuntu-2404 | Unit tests need RAM |
| `android-build` | blacksmith-4vcpu-ubuntu-2404 | APK assembly needs RAM |
| `ios-test` | macos-14 | M1 ARM64, 3x faster than macos-13 Intel |
| `ios-compile` | macos-14 | Same — Apple Silicon for native simulator |
| `mobile-ci-passed` | blacksmith-2vcpu-ubuntu-2404 | Summary gate, <30s |

**macos-14 NOT macos-13:** Intel runners are 3x slower. `iosSimulatorArm64Test` requires ARM64 host for native execution.

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
| Blacksmith runners (vs ubuntu-latest) | ~33% cheaper/min + faster = compound |
| Concurrency cancel-in-progress | ~30% fewer runs on busy PRs |
| Config-cache encryption key | ~30% faster (config phase skipped on cache hit) |
| Gradle + Konan cache | ~40% faster builds (4-5min → 2-3min) |
| Label-based skip + tiered CI | Skip iOS builds on Android-only PRs (~50% macOS minutes) |
| Build parallel to test | -5 to -15min from critical path |
| Job combining (lint+test on same runner) | Reduce per-minute rounding waste |
| `macos-14` vs `macos-13` | 3x faster iOS jobs = fewer macOS minutes |
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