# KMP Mobile CI Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure monolithic `mobile.yml` into entry + reusable workflows + composite action with Blacksmith Sticky Disks for maximum build acceleration.

**Architecture:** Entry workflow (`mobile-ci.yml`) dispatches to 3 reusable workflows (`mobile-build.yml`, `mobile-test.yml`, `mobile-lint.yml`) + nightly cache warm (`mobile-nightly.yml`). Single composite action (`setup-java-gradle`) replaces old `setup-android` with setup-gradle@v6 + cache encryption + Sticky Disks. Summary gate job (`mobile-ci-passed`) as sole required status check.

**Tech Stack:** GitHub Actions, Blacksmith runners (ARM), Sticky Disks, Gradle 8.14, Kotlin 2.1.21, setup-gradle@v6

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `.github/actions/setup-android/action.yml` | **Delete** | Replaced by `setup-java-gradle` |
| `.github/actions/setup-java-gradle/action.yml` | **Create** | Composite: JDK 17 + setup-gradle@v6 + Sticky Disks |
| `.github/workflows/mobile.yml` | **Delete** | Replaced by `mobile-ci.yml` |
| `.github/workflows/mobile-ci.yml` | **Create** | Entry point: triggers, path filters, concurrency, tiered CI |
| `.github/workflows/mobile-build.yml` | **Create** | Reusable: Android APK + iOS framework builds |
| `.github/workflows/mobile-test.yml` | **Create** | Reusable: shared + Android + iOS tests + coverage |
| `.github/workflows/mobile-lint.yml` | **Create** | Reusable: ktlint |
| `.github/workflows/mobile-nightly.yml` | **Create** | Scheduled: cache warm + full CI on master |
| `mobile/gradle.properties` | **Modify** | Add `kotlin.incremental.native=true`, tune heap for CI |

---

### Task 1: Create `GRADLE_CACHE_ENCRYPTION_KEY` repo secret

**Files:**
- None (GitHub repo settings)

- [ ] **Step 1: Generate encryption key**

```bash
openssl rand -base64 16
```

Expected: random 24-char string like `fKLIcOtr1ieP7FwDspepqA==`

- [ ] **Step 2: Add as GitHub repo secret**

```bash
gh secret set GRADLE_CACHE_ENCRYPTION_KEY --repo Artiffusion-Inc/skating-biomechanics-ml --body "<key-from-step-1>"
```

- [ ] **Step 3: Verify secret exists**

```bash
gh secret list --repo Artiffusion-Inc/skating-biomechanics-ml | grep GRADLE_CACHE_ENCRYPTION_KEY
```

Expected: `GRADLE_CACHE_ENCRYPTION_KEY` in output

---

### Task 2: Create `setup-java-gradle` composite action

**Files:**
- Create: `.github/actions/setup-java-gradle/action.yml`

This replaces the old `.github/actions/setup-android/action.yml` with Sticky Disks + setup-gradle@v6 + cache encryption.

- [ ] **Step 1: Create composite action file**

```yaml
name: 'Setup Java + Gradle'
description: 'JDK 17 + Gradle cache (setup-gradle@v6) + Sticky Disks (~/.gradle, ~/.konan) + wrapper validation'

inputs:
  java-version:
    description: 'JDK version'
    default: '17'

runs:
  using: "composite"
  steps:
    - uses: gradle/actions/wrapper-validation@v3

    - uses: actions/setup-java@v5
      with:
        distribution: temurin
        java-version: ${{ inputs.java-version }}

    - uses: gradle/actions/setup-gradle@v6
      with:
        cache-provider: basic
        cache-encryption-key: ${{ secrets.GRADLE_CACHE_ENCRYPTION_KEY }}
        dependency-graph: generate-and-submit

    - name: Mount Gradle home sticky disk
      uses: useblacksmith/stickydisk@v1
      with:
        key: ${{ github.repository }}-gradle-home
        path: ~/.gradle

    - name: Mount Kotlin/Native sticky disk
      uses: useblacksmith/stickydisk@v1
      with:
        key: ${{ github.repository }}-konan
        path: ~/.konan

    - name: Make gradlew executable
      shell: bash
      run: chmod +x mobile/gradlew
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/actions/setup-java-gradle/action.yml'))"
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add .github/actions/setup-java-gradle/action.yml
git commit -m "ci(mobile): add setup-java-gradle composite action with Sticky Disks"
```

---

### Task 3: Update `mobile/gradle.properties` for CI tuning

**Files:**
- Modify: `mobile/gradle.properties`

Add `kotlin.incremental.native=true` for incremental klib compilation. Keep existing settings.

- [ ] **Step 1: Add incremental native compilation**

Append to `mobile/gradle.properties`:
```properties
kotlin.incremental.native=true
```

- [ ] **Step 2: Verify file is valid**

```bash
grep "kotlin.incremental.native" mobile/gradle.properties
```

Expected: `kotlin.incremental.native=true`

- [ ] **Step 3: Commit**

```bash
git add mobile/gradle.properties
git commit -m "ci(mobile): enable kotlin.incremental.native for faster iOS builds"
```

---

### Task 4: Create `mobile-lint.yml` reusable workflow

**Files:**
- Create: `.github/workflows/mobile-lint.yml`

- [ ] **Step 1: Create reusable lint workflow**

```yaml
name: Mobile Lint

on:
  workflow_call:
    inputs:
      should-run:
        required: false
        default: true
        type: boolean

permissions:
  contents: read

jobs:
  android-lint:
    name: Android lint
    if: inputs.should-run
    runs-on: blacksmith-2vcpu-ubuntu-2404-arm
    timeout-minutes: 10
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Run ktlint
        run: ./gradlew ktlintCheck
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mobile-lint.yml'))"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile-lint.yml
git commit -m "ci(mobile): add mobile-lint.yml reusable workflow"
```

---

### Task 5: Create `mobile-test.yml` reusable workflow

**Files:**
- Create: `.github/workflows/mobile-test.yml`

Includes shared tests, Android tests with Kover coverage, and iOS simulator tests.

- [ ] **Step 1: Create reusable test workflow**

```yaml
name: Mobile Test

on:
  workflow_call:
    inputs:
      should-run-shared:
        required: false
        default: true
        type: boolean
      should-run-android:
        required: false
        default: true
        type: boolean
      should-run-ios:
        required: false
        default: false
        type: boolean
    secrets:
      CODECOV_TOKEN:
        required: false

permissions:
  contents: read

jobs:
  shared-test:
    name: Shared tests
    if: inputs.should-run-shared
    runs-on: blacksmith-4vcpu-ubuntu-2404-arm
    timeout-minutes: 15
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Run shared module tests
        run: ./gradlew :shared:testDebugUnitTest
      - name: Generate Kover coverage
        if: success()
        run: ./gradlew :shared:koverXmlReport
      - name: Upload coverage
        if: success()
        uses: actions/upload-artifact@v7
        with:
          name: shared-coverage-xml
          path: mobile/shared/build/reports/kover/report.xml
          retention-days: 14
      - name: Upload to Codecov
        if: success()
        uses: codecov/codecov-action@v6
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: mobile/shared/build/reports/kover/report.xml
          flags: shared
          fail_ci_if_error: false

  android-test:
    name: Android tests
    if: inputs.should-run-android
    runs-on: blacksmith-4vcpu-ubuntu-2404-arm
    timeout-minutes: 15
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Compile debug Kotlin
        run: ./gradlew :androidApp:compileDebugKotlin
      - name: Run Android unit tests
        run: ./gradlew :androidApp:testDebugUnitTest
      - name: Generate Kover coverage
        if: success()
        run: ./gradlew :androidApp:koverXmlReportDebug
      - name: Upload coverage
        if: success()
        uses: actions/upload-artifact@v7
        with:
          name: android-coverage-xml
          path: mobile/androidApp/build/reports/kover/debug/report.xml
          retention-days: 14
      - name: Upload to Codecov
        if: success()
        uses: codecov/codecov-action@v6
        with:
          token: ${{ secrets.CODECOV_TOKEN }}
          files: mobile/androidApp/build/reports/kover/debug/report.xml
          flags: android
          fail_ci_if_error: false

  ios-test:
    name: iOS tests
    if: inputs.should-run-ios
    runs-on: macos-14
    timeout-minutes: 20
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Run iOS simulator tests
        run: ./gradlew :shared:iosSimulatorArm64Test
      - name: Upload test reports
        if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: ios-test-reports
          path: mobile/shared/build/reports/tests/
          retention-days: 14
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mobile-test.yml'))"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile-test.yml
git commit -m "ci(mobile): add mobile-test.yml reusable workflow with iOS tests"
```

---

### Task 6: Create `mobile-build.yml` reusable workflow

**Files:**
- Create: `.github/workflows/mobile-build.yml`

Build parallel to tests. Android build on 4vcpu with project-level sticky disk. iOS framework for simulator only (CI speed).

- [ ] **Step 1: Create reusable build workflow**

```yaml
name: Mobile Build

on:
  workflow_call:
    inputs:
      should-run-android:
        required: false
        default: true
        type: boolean
      should-run-ios:
        required: false
        default: false
        type: boolean

permissions:
  contents: read

jobs:
  android-build:
    name: Android debug build
    if: inputs.should-run-android
    runs-on: blacksmith-4vcpu-ubuntu-2404-arm
    timeout-minutes: 15
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Mount Android project build cache
        uses: useblacksmith/stickydisk@v1
        with:
          key: ${{ github.repository }}-android-build-cache
          path: mobile/.gradle
      - name: Build debug APK
        run: ./gradlew assembleDebug
      - uses: actions/upload-artifact@v7
        with:
          name: apk-debug
          path: mobile/androidApp/build/outputs/apk/debug/*.apk
          retention-days: 7

  ios-build:
    name: iOS framework build
    if: inputs.should-run-ios
    runs-on: macos-14
    timeout-minutes: 20
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Link debug framework (simulator)
        run: ./gradlew :shared:linkDebugFrameworkIosSimulatorArm64
      - uses: actions/upload-artifact@v7
        with:
          name: ios-framework-debug
          path: mobile/shared/build/bin/iosSimulatorArm64/debugFramework/
          retention-days: 14
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mobile-build.yml'))"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile-build.yml
git commit -m "ci(mobile): add mobile-build.yml reusable workflow with project sticky disk"
```

---

### Task 7: Create `mobile-ci.yml` entry point

**Files:**
- Create: `.github/workflows/mobile-ci.yml`

Entry point with path filters, concurrency, tiered CI (fast on PR / full on merge queue), summary gate.

- [ ] **Step 1: Create entry workflow**

```yaml
name: Mobile CI

on:
  push:
    branches: [master]
    paths:
      - 'mobile/**'
      - 'backend/app/**'
      - 'ml/src/analysis/**'
      - '.github/workflows/mobile*.yml'
      - '.github/actions/setup-java-gradle/**'
  pull_request:
    branches: [master]
    paths:
      - 'mobile/**'
      - 'backend/app/**'
      - 'ml/src/analysis/**'
      - '.github/workflows/mobile*.yml'
      - '.github/actions/setup-java-gradle/**'
  merge_group:
  workflow_dispatch:
    inputs:
      run-all:
        description: 'Run all jobs regardless of changed files'
        default: false
        type: boolean

permissions:
  contents: read
  pull-requests: read

concurrency:
  group: mobile-ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/master' }}

jobs:
  changes:
    name: Detect changes
    runs-on: blacksmith-2vcpu-ubuntu-2404-arm
    timeout-minutes: 2
    outputs:
      shared: ${{ steps.filter.outputs.shared }}
      android: ${{ steps.filter.outputs.android }}
      ios: ${{ steps.filter.outputs.ios }}
    steps:
      - uses: actions/checkout@v6
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          filters: |
            shared:
              - 'mobile/shared/**'
              - 'mobile/build-logic/**'
              - 'mobile/gradle/**'
              - 'mobile/build.gradle.kts'
              - 'mobile/settings.gradle.kts'
              - 'mobile/gradle.properties'
              - 'backend/app/**'
              - 'ml/src/analysis/**'
            android:
              - 'mobile/androidApp/**'
              - 'mobile/build-logic/**'
              - 'mobile/gradle/**'
              - 'mobile/build.gradle.kts'
              - 'mobile/settings.gradle.kts'
              - 'mobile/gradle.properties'
              - 'mobile/proto/**'
            ios:
              - 'mobile/shared/**'
              - 'mobile/iosApp/**'
              - 'mobile/build-logic/**'
              - 'mobile/gradle/**'
              - 'mobile/build.gradle.kts'
              - 'mobile/settings.gradle.kts'
              - 'mobile/gradle.properties'

  lint:
    name: Lint
    needs: changes
    if: ${{ inputs.run-all || needs.changes.outputs.android == 'true' }}
    uses: ./.github/workflows/mobile-lint.yml
    with:
      should-run: ${{ inputs.run-all || needs.changes.outputs.android == 'true' }}
    secrets: inherit

  test:
    name: Test
    needs: changes
    uses: ./.github/workflows/mobile-test.yml
    with:
      should-run-shared: ${{ inputs.run-all || needs.changes.outputs.shared == 'true' }}
      should-run-android: ${{ inputs.run-all || needs.changes.outputs.android == 'true' }}
      should-run-ios: ${{ inputs.run-all || needs.changes.outputs.ios == 'true' || github.event_name == 'merge_group' || contains(github.event.pull_request.labels.*.name, 'run-ios-tests') }}
    secrets: inherit

  build:
    name: Build
    needs: changes
    if: ${{ inputs.run-all || needs.changes.outputs.android == 'true' || needs.changes.outputs.ios == 'true' || github.event_name == 'merge_group' }}
    uses: ./.github/workflows/mobile-build.yml
    with:
      should-run-android: ${{ inputs.run-all || needs.changes.outputs.android == 'true' || github.event_name == 'merge_group' }}
      should-run-ios: ${{ inputs.run-all || needs.changes.outputs.ios == 'true' || github.event_name == 'merge_group' }}
    secrets: inherit

  mobile-ci-passed:
    name: Mobile CI Passed
    needs: [changes, lint, test, build]
    if: always()
    runs-on: blacksmith-2vcpu-ubuntu-2404-arm
    timeout-minutes: 2
    steps:
      - name: Evaluate results
        run: |
          echo "lint: ${{ needs.lint.result }}"
          echo "test: ${{ needs.test.result }}"
          echo "build: ${{ needs.build.result }}"
          for result in "${{ needs.lint.result }}" "${{ needs.test.result }}" "${{ needs.build.result }}"; do
            if [[ "$result" == "failure" || "$result" == "cancelled" ]]; then
              echo "::error::A required mobile CI job failed with result: $result"
              exit 1
            fi
          done
          echo "All mobile checks passed"
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mobile-ci.yml'))"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile-ci.yml
git commit -m "ci(mobile): add mobile-ci.yml entry point with tiered CI and summary gate"
```

---

### Task 8: Create `mobile-nightly.yml` cache warm workflow

**Files:**
- Create: `.github/workflows/mobile-nightly.yml`

Scheduled cache warm + full CI validation on master.

- [ ] **Step 1: Create nightly workflow**

```yaml
name: Mobile Nightly

on:
  schedule:
    - cron: "3 4 * * *"
  push:
    branches: [master]
    paths:
      - 'mobile/gradle/**'
      - 'mobile/build-logic/**'
      - 'mobile/gradle.properties'
  workflow_dispatch:

permissions:
  contents: read

jobs:
  gradle-cache-warm:
    name: Gradle cache warm
    runs-on: blacksmith-4vcpu-ubuntu-2404-arm
    timeout-minutes: 10
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Populate Gradle caches
        run: ./gradlew :shared:dependencies :androidApp:dependencies --configuration-cache

  konan-cache-warm:
    name: Kotlin/Native cache warm
    runs-on: macos-14
    timeout-minutes: 15
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-java-gradle
      - name: Populate Konan caches
        run: ./gradlew :shared:compileKotlinIosSimulatorArm64 --configuration-cache

  full-ci:
    name: Full CI
    needs: [gradle-cache-warm, konan-cache-warm]
    uses: ./.github/workflows/mobile-ci.yml
    with:
      run-all: true
    secrets: inherit
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mobile-nightly.yml'))"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile-nightly.yml
git commit -m "ci(mobile): add mobile-nightly.yml for cache warm + full CI validation"
```

---

### Task 9: Delete old `mobile.yml` and `setup-android`

**Files:**
- Delete: `.github/workflows/mobile.yml`
- Delete: `.github/actions/setup-android/action.yml`

- [ ] **Step 1: Delete old mobile.yml**

```bash
git rm .github/workflows/mobile.yml
```

- [ ] **Step 2: Delete old setup-android composite action**

```bash
git rm .github/actions/setup-android/action.yml
```

- [ ] **Step 3: Remove empty directory if needed**

```bash
rmdir .github/actions/setup-android/ 2>/dev/null || true
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "ci(mobile): remove old mobile.yml and setup-android action (replaced by restructured CI)"
```

---

### Task 10: Validate all workflow files and push

**Files:**
- All `.github/workflows/mobile*.yml`
- `.github/actions/setup-java-gradle/action.yml`

- [ ] **Step 1: Validate all YAML files parse correctly**

```bash
for f in .github/workflows/mobile*.yml .github/actions/setup-java-gradle/action.yml; do
  python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"
done
```

Expected: all files show `OK`

- [ ] **Step 2: Verify no references to deleted files remain**

```bash
grep -r "setup-android\|mobile\.yml" .github/ --include="*.yml" --include="*.yaml" 2>/dev/null
```

Expected: no output (no stale references)

- [ ] **Step 3: Verify all new files exist**

```bash
ls -la .github/workflows/mobile-ci.yml .github/workflows/mobile-build.yml .github/workflows/mobile-test.yml .github/workflows/mobile-lint.yml .github/workflows/mobile-nightly.yml .github/actions/setup-java-gradle/action.yml
```

Expected: all 6 files exist

- [ ] **Step 4: Push branch and create PR**

```bash
git push -u origin worktree-fix-internet-permission
gh pr create --title "ci(mobile): restructure mobile CI with Sticky Disks and tiered builds" --body "$(cat <<'EOF'
## Summary
- Restructure monolithic `mobile.yml` into entry + 3 reusable workflows + nightly cache warm
- Replace `setup-android` composite action with `setup-java-gradle` (setup-gradle@v6 + Sticky Disks)
- Add `GRADLE_CACHE_ENCRYPTION_KEY` for configuration cache persistence (was silently discarded)
- Add Blacksmith Sticky Disks for `~/.gradle`, `~/.konan`, `mobile/.gradle` (~3s access vs 15-66s cache)
- Add `iosSimulatorArm64Test` job on `macos-14`
- Build parallel to tests (remove serial dependency `android-build → android-test`)
- Add tiered CI: fast on PR, full on merge queue
- Add summary gate job `Mobile CI Passed` as sole required status check
- Add `kotlin.incremental.native=true` for faster iOS builds
- Add `timeout-minutes` on all jobs
- Label `run-ios-tests` opts into iOS tests on PR

## Test plan
- [ ] Push to PR and verify `mobile-ci.yml` triggers correctly
- [ ] Verify Sticky Disks mount in CI logs (3s access)
- [ ] Verify configuration cache is saved (look for "Saving configuration cache" in logs)
- [ ] Verify `iosSimulatorArm64Test` runs on `macos-14`
- [ ] Verify `android-build` runs parallel to `android-test`
- [ ] Verify `Mobile CI Passed` summary gate works
- [ ] Delete old `mobile.yml` after validation
EOF
)"
```

---

### Task 11: Update branch protection (post-merge)

This task must be done after the PR is merged, from the GitHub UI or CLI.

- [ ] **Step 1: Set `Mobile CI Passed` as required status check**

```bash
gh api repos/Artiffusion-Inc/skating-biomechanics-ml/branches/master/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["Mobile CI Passed"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1}' \
  --field restrictions=null
```

- [ ] **Step 2: Enable merge queue on master**

In GitHub repo Settings → Branches → Protection rules → `master` → enable "Merge queue".

- [ ] **Step 3: Verify old status checks are no longer required**

Ensure `shared-test`, `android-lint`, `android-test`, `android-build-debug`, `ios-compile` are NOT in the required checks list.

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
|---|---|
| `GRADLE_CACHE_ENCRYPTION_KEY` secret | Task 1 |
| `setup-java-gradle` composite action | Task 2 |
| Sticky Disks (~/.gradle, ~/.konan, mobile/.gradle) | Task 2, Task 6 |
| `kotlin.incremental.native=true` | Task 3 |
| `mobile-lint.yml` reusable | Task 4 |
| `mobile-test.yml` reusable (shared + android + ios) | Task 5 |
| `mobile-build.yml` reusable (android + ios) | Task 6 |
| `mobile-ci.yml` entry point | Task 7 |
| `mobile-nightly.yml` cache warm | Task 8 |
| Delete old `mobile.yml` + `setup-android` | Task 9 |
| Validation + push | Task 10 |
| Branch protection update | Task 11 |
| Tiered CI (PR vs merge queue) | Task 7 (in mobile-ci.yml) |
| Label-based iOS opt-in | Task 7 (in mobile-ci.yml) |
| Summary gate `Mobile CI Passed` | Task 7 (in mobile-ci.yml) |
| Build parallel to test | Task 7 (no `needs: android-test` on build) |
| `timeout-minutes` | Tasks 4-8 |
| Blacksmith runners | Tasks 2-8 |
| Wrapper validation | Task 2 (in composite action) |
| Dependency graph | Task 2 (setup-gradle@v6) |

**2. Placeholder scan:** No TBD/TODO found. All steps have complete code.

**3. Type consistency:** `inputs.should-run-*` in reusable workflows match the calling convention in `mobile-ci.yml`. Composite action uses `inputs.java-version` consistently. Sticky disk keys use `github.repository` prefix consistently.
