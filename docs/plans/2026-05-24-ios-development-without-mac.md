# iOS Development Without Mac — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add iOS compilation to CI so every push validates KMP shared code compiles under Kotlin/Native, preparing for future iOS development without macOS hardware.

**Architecture:** Phase 1 only (CI compile-only). Add `binaries.framework` to KMP shared module, add `ios-compile` CI job on macOS runner. No Xcode project, no .ipa, no TestFlight — those are Phase 2-4 per the spec.

**Tech Stack:** Kotlin Multiplatform, Kotlin/Native, GitHub Actions macOS runner, Gradle 8.14

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `mobile/shared/build.gradle.kts` | Modify | Add `binaries.framework` block |
| `mobile/build-logic/convention/src/main/kotlin/kmp-library-convention.gradle.kts` | Modify | Move `binaries.framework` here (convention plugin) |
| `.github/workflows/mobile.yml` | Modify | Add `ios-compile` job |
| `.github/actions/setup-android/action.yml` | Modify | Add Kotlin/Native cache key |

---

### Task 1: Add `binaries.framework` to KMP convention plugin

The `kmp-library-convention.gradle.kts` declares iOS targets but no framework binary output. Without this, `compileKotlinIosArm64` succeeds but produces nothing Xcode can consume.

**Files:**

- Modify: `mobile/build-logic/convention/src/main/kotlin/kmp-library-convention.gradle.kts`

- [ ] **Step 1: Add `binaries.framework` block**

Replace the `kotlin {}` block (lines 8-16) with:

```kotlin
kotlin {
    androidTarget {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }
    iosArm64()
    iosSimulatorArm64()

    binaries.framework {
        baseName = "shared"
        isStatic = true
    }
}
```

- [ ] **Step 2: Verify shared module builds with framework output**

Run: `cd mobile && ./gradlew :shared:linkDebugFrameworkIosArm64 --dry-run`
Expected: Task listed in dry-run output, no errors.

- [ ] **Step 3: Commit**

```bash
git add mobile/build-logic/convention/src/main/kotlin/kmp-library-convention.gradle.kts
git commit -m "feat(kmp): add binaries.framework for iOS shared module

Static framework output enables Xcode linking.
isStatic=true required for App Store distribution."
```

---

### Task 2: Verify existing shared module compiles for iOS

Confirm the framework configuration doesn't break anything and that Kotlin/Native compilation works.

**Files:** None (verification only)

- [ ] **Step 1: Compile iOS Arm64 target**

Run: `cd mobile && ./gradlew :shared:compileKotlinIosArm64`
Expected: BUILD SUCCESSFUL

- [ ] **Step 2: Link debug framework for Arm64**

Run: `cd mobile && ./gradlew :shared:linkDebugFrameworkIosArm64`
Expected: BUILD SUCCESSFUL, `mobile/shared/build/bin/iosArm64/debugFramework/shared.framework/` exists.

- [ ] **Step 3: Compile iOS Simulator Arm64 target**

Run: `cd mobile && ./gradlew :shared:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Link debug framework for Simulator Arm64**

Run: `cd mobile && ./gradlew :shared:linkDebugFrameworkIosSimulatorArm64`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Verify Android still builds**

Run: `cd mobile && ./gradlew :shared:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Verify Android unit tests still pass**

Run: `cd mobile && ./gradlew :shared:testDebugUnitTest`
Expected: All tests pass.

---

### Task 3: Add `ios-compile` CI job to mobile.yml

Add a macOS-runner job that compiles KMP iOS targets and links frameworks on every push/PR touching `mobile/`.

**Files:**

- Modify: `.github/workflows/mobile.yml`

- [ ] **Step 1: Add `ios` filter to changes job**

In the `changes` job, after the `android:` filter (line 56), add:

```yaml
            ios:
              - 'mobile/shared/**'
              - 'mobile/iosApp/**'
              - 'mobile/build-logic/**'
              - 'mobile/gradle/**'
              - 'mobile/build.gradle.kts'
              - 'mobile/settings.gradle.kts'
              - 'mobile/gradle.properties'
```

Also update the `outputs` section (line 36-37) to add:

```yaml
      ios: ${{ steps.filter.outputs.ios }}
```

- [ ] **Step 2: Add `ios-compile` job**

After the `android-build-debug` job (after line 175), add:

```yaml
  # ── iOS compile ─────────────────────────────────────────────
  ios-compile:
    name: iOS compile
    needs: changes
    if: needs.changes.outputs.ios == 'true'
    runs-on: macos-14
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: 17

      - uses: gradle/actions/setup-gradle@v4
        with:
          cache-read-only: ${{ github.ref != 'refs/heads/master' }}

      - name: Cache Kotlin/Native compiler
        uses: actions/cache@v4
        with:
          path: ~/.konan
          key: konan-${{ runner.os }}-${{ hashFiles('mobile/gradle/libs.versions.toml') }}
          restore-keys: konan-${{ runner.os }}-

      - name: Compile iOS Arm64
        run: ./gradlew :shared:compileKotlinIosArm64

      - name: Compile iOS Simulator Arm64
        run: ./gradlew :shared:compileKotlinIosSimulatorArm64

      - name: Link debug framework iOS Arm64
        run: ./gradlew :shared:linkDebugFrameworkIosArm64

      - name: Link release framework iOS Arm64
        run: ./gradlew :shared:linkReleaseFrameworkIosArm64
```

- [ ] **Step 3: Verify workflow YAML is valid**

Run: `cd /home/michael/Github/skating-biomechanics-ml && actionlint .github/workflows/mobile.yml`
Expected: No errors. (If actionlint not installed, verify YAML syntax manually.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/mobile.yml
git commit -m "ci(mobile): add iOS compile job on macOS runner

Compiles KMP shared module for iosArm64 + iosSimulatorArm64.
Links debug+release frameworks. Catches iOS-specific Kotlin/Native
errors on every push. Uses macos-14 runner with Kotlin/Native cache."
```

---

### Task 4: Add `iosApp/` to path triggers in mobile.yml

The `on.push.paths` and `on.pull_request.paths` triggers should include `iosApp/` changes since they affect iOS builds.

**Files:**

- Modify: `.github/workflows/mobile.yml`

- [ ] **Step 1: Add `iosApp` path to trigger filters**

In the `on.push.paths` and `on.pull_request.paths` sections (lines 7-9 and 15-17), add:

```yaml
      - 'mobile/iosApp/**'
```

After the existing `mobile/**` entry in each section.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/mobile.yml
git commit -m "ci(mobile): trigger iOS CI on iosApp/ changes"
```

---

### Task 5: Push and verify CI passes

Push the branch to GitHub and verify the new `ios-compile` job runs successfully.

**Files:** None

- [ ] **Step 1: Push branch to remote**

Run: `git push -u origin worktree-ios-dev-spec`

- [ ] **Step 2: Check CI status**

Run: `gh run list --workflow mobile.yml --limit 3`
Expected: New run triggered, `ios-compile` job appears and passes.

- [ ] **Step 3: If CI fails, debug and fix**

Check logs: `gh run view <run-id> --log-failed`
Fix the issue, commit, push again.

---

## Self-Review

**Spec coverage:**
- Phase 1 (CI compile-only): ✅ Tasks 1-5
- Phase 2 (Xcode project + .ipa): Not in this plan — deferred per spec ("when iOS dev starts")
- Phase 3 (AltServer-Linux): Not in this plan — deferred
- Phase 4 (TestFlight): Not in this plan — deferred

**Placeholder scan:** No TBD/TODO found. All code shown inline.

**Type consistency:** `binaries.framework { baseName = "shared"; isStatic = true }` matches Gradle task names (`:shared:linkDebugFrameworkIosArm64`, etc.) used in CI.