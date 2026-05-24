# KMP Mobile CI Restructure

**Date:** 2026-05-24
**Status:** Draft
**Scope:** `mobile.yml` workflow → restructured entry + reusable workflows + composite actions

## Problem

Current `mobile.yml` is monolithic (5+ jobs, ~200 lines). No composite actions, no reusable workflows, no concurrency control, no Gradle caching, no iOS tests. GitHub Actions billing exhausted — need cost efficiency.

Best practices from [AKJAW/kotlin-multiplatform-github-actions](https://github.com/AKJAW/kotlin-multiplatform-github-actions):
- Entry workflow + reusable workflows via `workflow_call`
- Composite actions for setup duplication elimination
- Label-based conditional builds
- Concurrency: cancel in-progress on feature branches
- Platform-appropriate runners (ubuntu for Android, macos for iOS)

## Architecture

```
.github/
├── workflows/
│   ├── mobile-ci.yml            ← entry point (triggers, labels, concurrency, dispatches)
│   ├── mobile-build.yml         ← reusable: Android APK + iOS framework compilation
│   ├── mobile-test.yml          ← reusable: shared + Android + iOS tests + coverage
│   └── mobile-lint.yml          ← reusable: ktlint
└── actions/
    ├── setup-java-gradle/       ← composite: JDK 17 + Gradle wrapper + cache
    │   └── action.yml
    └── setup-ios/               ← composite: CocoaPods + generateDummyFramework
        └── action.yml
```

## Workflow Details

### mobile-ci.yml (entry point)

**Triggers:**
- `push` to `master` (paths: `mobile/**`)
- `pull_request` (paths: `mobile/**`)
- Manual `workflow_dispatch` with platform selectors

**Concurrency:**
```yaml
concurrency:
  group: mobile-ci-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}
```

**SetUp job:** Detect changed modules via `dorny/paths-filter` + PR labels.

Labels: `KMP`, `android`, `ios`. Master branch → always all platforms.

Outputs: `shouldRunShared`, `shouldRunAndroid`, `shouldRunIos`

**Downstream jobs:** Call reusable workflows with `shouldRun*` outputs.

### mobile-build.yml (reusable)

`on: workflow_call` with inputs: `shouldRunAndroid`, `shouldRunIos`

**Jobs:**
- `android-build` (ubuntu-latest): `./gradlew :androidApp:assembleDebug` → upload APK artifact
- `ios-compile` (macos-13): `setup-ios` composite → `./gradlew :shared:linkDebugFrameworkIosArm64` + `:shared:linkDebugFrameworkIosSimulatorArm64`

Both use `setup-java-gradle` composite action.

### mobile-test.yml (reusable)

`on: workflow_call` with inputs: `shouldRunShared`, `shouldRunAndroid`, `shouldRunIos`

**Jobs:**
- `shared-test` (ubuntu-latest): `./gradlew :shared:allTests` → coverage upload
- `android-test` (ubuntu-latest): `./gradlew :androidApp:testDebugUnitTest` → Kover coverage
- `ios-test` (macos-13): `setup-ios` → `./gradlew :shared:iosSimulatorArm64Test` → junit xml

All use `setup-java-gradle` composite action.

### mobile-lint.yml (reusable)

`on: workflow_call` with input: `shouldRunAndroid`

**Jobs:**
- `android-lint` (ubuntu-latest): `./gradlew :androidApp:ktlintCheck`

## Composite Actions

### setup-java-gradle

```yaml
name: Setup Java + Gradle
inputs:
  java-version:
    default: '17'
runs:
  using: composite
  steps:
    - uses: actions/setup-java@v4
      with:
        distribution: temurin
        java-version: ${{ inputs.java-version }}
    - uses: actions/cache@v4
      with:
        path: |
          ~/.gradle/caches
          ~/.gradle/gradle-user-home
          ~/.konan
        key: gradle-${{ runner.os }}-${{ hashFiles('mobile/**/*.gradle.kts', 'mobile/gradle/libs.versions.toml') }}
        restore-keys: gradle-${{ runner.os }}-
    - name: Gradle wrapper validation
      uses: gradle/actions/wrapper-validation@v4
    - name: Make gradlew executable
      shell: bash
      run: chmod +x mobile/gradlew
```

### setup-ios

```yaml
name: Setup iOS build environment
runs:
  using: composite
  steps:
    - name: Generate dummy KMP framework
      shell: bash
      run: cd mobile && ./gradlew :shared:generateDummyFramework
    - uses: maxim-lobanov/setup-cocoapods@v1
      with:
        version: latest
    - name: Pod install
      shell: bash
      run: cd mobile/iosApp && pod install --verbose
```

## Caching Strategy

| Cache target | Path | Key basis | Restore fallback |
|---|---|---|---|
| Gradle caches | `~/.gradle/caches` | OS + gradle.kts + toml hash | OS prefix |
| Gradle user home | `~/.gradle/gradle-user-home` | (same) | (same) |
| Kotlin/Native | `~/.konan` | (same) | (same) |

Configuration cache enabled via `mobile/gradle.properties`:
```properties
org.gradle.configuration-cache=true
org.gradle.parallel=true
org.gradle.caching=true
```

## iOS Test Coverage

New job `ios-test` in `mobile-test.yml`:
- Runner: `macos-13` (arm64 simulator)
- Command: `./gradlew :shared:iosSimulatorArm64Test`
- Requires `setup-ios` composite action (generateDummyFramework + CocoaPods)
- Test results: junit xml → `actions/upload-artifact`
- Coverage: not integrated in v1 (Kover doesn't support iOS; xcresult coverage is separate effort)

## Cost Savings

| Technique | Estimated saving |
|---|---|
| Concurrency cancel-in-progress | ~30% fewer runs on busy PRs |
| Gradle cache | ~40% faster builds (4-5min → 2-3min) |
| Label-based skip | Skip iOS builds on Android-only PRs (~50% minutes on some PRs) |
| Path filters (already present) | Skip entire mobile CI on backend-only PRs |

## Migration Plan

1. Create composite actions (`.github/actions/`)
2. Create `mobile-build.yml`, `mobile-test.yml`, `mobile-lint.yml` reusable workflows
3. Create `mobile-ci.yml` entry point
4. Test `mobile-ci.yml` on a feature branch
5. Delete `mobile.yml` (mobile-ci.yml fully replaces it)

## Out of Scope

- Release signing / Play Store / TestFlight deployment
- Backend / frontend CI changes
- Self-hosted runners
- Android instrumented tests (require emulator)
