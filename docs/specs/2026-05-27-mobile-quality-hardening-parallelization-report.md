# Mobile Quality Hardening — Parallelization Research Report

Date: 2026-05-27
Source: 3 specialized research agents (i18n, security, accessibility)
Spec: `docs/specs/2026-05-27-mobile-quality-hardening-design.md`

---

## Executive Summary

The 4-wave spec can be **significantly parallelized**. The original dependency chain (Wave 0 → Wave 1 → Wave 2 → Wave 3) is overly conservative. In reality:

- **Wave 0** (AppError) takes ~30 min and unblocks everything
- **Wave 1** (i18n) can be split across 5+ parallel agents by screen/feature
- **Wave 2** (Accessibility) is **70% independent** of Wave 1 — structural semantics, touch targets, `enableAccessibilityChecks()` can start immediately
- **Wave 3** (Security) tasks are fully independent of each other and of Wave 2
- **Critical spec corrections needed:** ProGuard rules contain anti-pattern, NSC template needs improvements

**Revised wall-clock estimate:** 4-5 hours parallelized (vs 10-12 hours sequential).

---

## 1. Key Spec Corrections

### 1.1 ProGuard Rules Anti-Pattern (CRITICAL)

**Spec section 3.1** proposes `-keep class io.ktor.** { *; }`. This is an **anti-pattern** per Android Developer Blog — it completely nullifies R8's benefits for the entire Ktor package, keeping thousands of unused internal classes.

**Correction:** Use narrow keeps:
```proguard
# BAD (spec): -keep class io.ktor.** { *; }
# GOOD: Only keep what's needed for reflection-based plugin loading
-keep class io.ktor.client.plugins.** { *; }
```

**Consumer rules already bundled:** kotlinx.serialization (v1.8.1), Room, Hilt, CameraX, WorkManager, OkHttp, kotlinx.coroutines all ship `META-INF/proguard/` consumer rules. R8 auto-merges these. Manual rules needed only for Ktor, Kable, and SkateLab models.

### 1.2 Network Security Config Improvements

The spec's NSC template is missing:
1. **`cleartextTrafficPermitted="false"`** — blocks HTTP on API domain
2. **`expiration` attribute on `<pin-set>`** — prevents permanent lockout if app can't update
3. **System certs in `<debug-overrides>`** — needed alongside user certs

### 1.3 BleScanViewModel Status Strings (NOT AppError)

Agent 1 and Agent 3 both flagged: `BleScanViewModel` has UI status strings (`"Сброс лев..."`) in `StateFlow<String>`. These are **not errors** — they're status labels. They need a `BleScanStatus` enum, not `AppError`. Same pattern as AppError but for non-error states.

---

## 2. Revised Dependency Graph

```
                    ┌─────────────────────────────────┐
                    │ Wave 0: AppError + fallbackTo…  │
                    │ (30 min, sequential foundation)  │
                    └──────────┬──────────────────────┘
                               │
          ┌────────────────────┼───────────────────────┐
          ▼                    ▼                        ▼
   ┌──────────────┐  ┌─────────────────┐  ┌──────────────────────┐
   │ Wave 1: i18n │  │ Wave 2: A11y    │  │ Wave 3: Security     │
   │ (split 5     │  │ (70% parallel   │  │ (4 parallel tasks)   │
   │  agents)     │  │  with Wave 1)   │  │                      │
   └──────┬───────┘  └───────┬─────────┘  └──────┬───────────────┘
          │                  │                    │
          │    ┌─────────────┘                    │
          ▼    ▼                                  ▼
   ┌──────────────────┐              ┌─────────────────────────┐
   │ Wave 2 remaining │              │ Wave 3E: Release build  │
   │ (30% needs i18n) │              │ verification             │
   └──────────────────┘              └──────┬──────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────────────┐
                                    │ Wave 3F: Baseline       │
                                    │ Profiles (P2, later)    │
                                    └─────────────────────────┘
```

---

## 3. Parallel Execution Plan

### Phase 1 — Foundation (30 min, sequential)

| Task | Duration | Files |
|------|----------|-------|
| Create `AppError.kt` sealed interface | 5 min | `shared/commonMain/models/AppError.kt` |
| Create `ExceptionMapping.kt` | 5 min | `shared/commonMain/utils/ExceptionMapping.kt` |
| Refactor ViewModels: `Error(AppError)` | 10 min | `SessionsViewModel.kt`, `AuthViewModel.kt`, `ProcessingViewModel.kt` |
| `fallbackToDestructiveMigration` debug guard | 5 min | `DatabaseModule.kt` |
| Write `AppErrorTest` | 5 min | `commonTest/models/AppErrorTest.kt` |

**Gate:** Phase 1 must complete before Phase 2 starts. But Phase 2 tasks can start immediately for parts that don't depend on AppError.

### Phase 2 — Parallel Waves (3-4 hours, heavily parallelized)

#### Stream A: i18n (split by screen/feature)

| Agent | Files | Strings | Duration |
|-------|-------|---------|----------|
| A1 | `BleScanScreen.kt` + `BleScanViewModel.kt` | ~14 | 30 min |
| A2 | `SessionDetailScreen.kt` + `SessionListScreen.kt` | ~42 | 45 min |
| A3 | `CalibrationScreen.kt` + `RecordingScreen.kt` | ~12 | 20 min |
| A4 | `LoginScreen.kt` + `RegisterScreen.kt` + `ProcessingScreen.kt` | ~10 | 20 min |
| A5 | `MoreScreen.kt` + `ProfileScreen.kt` + `CameraScreen.kt` | ~5 | 15 min |
| A6 | Error strings + `AppError.asString()` | ~10 | 20 min (waits for Phase 1) |

**Shared prerequisite:** Create `values/strings.xml` (English default) + `values-ru/strings.xml` (Russian) structure first (5 min).

#### Stream B: Accessibility (70% immediate, 30% after i18n)

| Task | Can Start | Duration | Dependency |
|------|-----------|----------|-------------|
| Add `ui-test-junit4-accessibility` dependency | Immediately | 5 min | None |
| Add `enableAccessibilityChecks()` to tests | Immediately | 15 min | None |
| Fix touch targets (remove `Modifier.size(32.dp)`) | Immediately | 10 min | None |
| Add `clearAndSetSemantics` on SkeletonOverlay | Immediately | 10 min | None |
| Add `semantics(mergeDescendants)` on MetricCard, SessionCard | Immediately | 15 min | None |
| Add `progressBarRangeInfo` on progress indicators | Immediately | 10 min | None |
| Add `liveRegion = LiveRegion.Polite` on error states | Immediately | 10 min | None |
| Create `BleScanStatus` enum (status strings, not errors) | Immediately | 15 min | None |
| Convert hardcoded Russian contentDescription → `stringResource()` | After i18n | 20 min | Wave 1 |
| Add localized chart/skeleton descriptions | After i18n | 15 min | Wave 1 |
| Font scaling test (`CompositionLocalProvider`) | After i18n | 15 min | Wave 1 |

#### Stream C: Security (4 fully parallel tasks)

| Task | Can Start | Duration | Dependency |
|------|-----------|----------|-------------|
| C1: Write ProGuard rules (narrow keeps) | Immediately | 30 min | None |
| C2: Create `network_security_config.xml` + Manifest | Immediately | 20 min | None |
| C3: API key safety audit | Immediately | 15 min | None |
| C4: APK size monitoring CI step | Immediately | 15 min | None |
| C5: Release build verification | After C1+C2 | 30 min | C1, C2 |
| C6: Baseline Profiles (P2) | After C5 | 1-2 hours | C5 |

---

## 4. Tool Recommendations

### i18n Tools

| Tool | Purpose | Status |
|------|---------|--------|
| Android Lint `HardcodedText` | **Discovery** — find all hardcoded strings | Use for inventory, not extraction |
| IntelliJ "Extract string resource" (Alt+Enter) | **Single-string extraction** | Best for incremental work |
| Custom grep script | **Batch discovery** of Russian strings | `grep -rn '[а-яА-Я]' mobile/androidApp/src/main/java/` |
| `compose.resources` (CMP 1.6+) | **Future KMP string resources** | Adopt when adding iOS; not needed now |

### Accessibility Tools

| Tool | Purpose | Status |
|------|---------|--------|
| `ui-test-junit4-accessibility` (Compose 1.8.0+) | **CI accessibility checks** | **Best finding** — automated in instrumented tests |
| Google Accessibility Scanner | Manual device scanning | Good for pre-release audit |
| Android Studio UI Checks (Iguana+) | Preview-based checks | Developer workflow, not CI |
| `CompositionLocalProvider(LocalDensity(fontScale=2f))` | Font scaling unit tests | Lightweight, no emulator needed |
| CVS Health accessibility techniques repo | Reference patterns | https://github.com/cvs-health/android-compose-accessibility-techniques |

### Security Tools

| Tool | Purpose | Status |
|------|---------|--------|
| R8 `-printseeds` / `-printusage` | Audit ProGuard rule breadth | Add to `proguard-rules.pro` |
| Diffuse (Jake Wharton) | APK size regression in PRs | P3 — add after Play Store |
| `apkanalyzer` | DEX/class count | Android SDK tool |
| Gradle Managed Devices | Baseline profile generation in CI | P2 — weekly workflow |

---

## 5. Revised ProGuard Rules (Replacing Spec Section 3.1)

```proguard
# ============================================================
# SkateLab ProGuard Rules — R8 Full Mode
# Strategy: Minimize manual rules. Prefer library consumer rules.
# ============================================================

# === kotlinx.serialization ===
# Consumer rules bundled since v1.7+. Explicit safety net:
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    static ** Companion;
}
-if @kotlinx.serialization.Serializable class ** {
    static **$* *;
}
-keepclassmembers class <2>$<3> {
    kotlinx.serialization.KSerializer serializer(...);
}
-if @kotlinx.serialization.Serializable class ** {
    public static ** INSTANCE;
}
-keepclassmembers class <1> {
    public static <1> INSTANCE;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclassmembers public class **$$serializer {
    private ** descriptor;
}
-keepattributes RuntimeVisibleAnnotations, AnnotationDefault
-dontnote kotlinx.serialization.**
-dontwarn kotlinx.serialization.internal.ClassValueReferences

# === Ktor Client ===
# No consumer rules. Narrow keeps only — do NOT use -keep class io.ktor.**
-keep class io.ktor.client.plugins.** { *; }
-dontwarn io.ktor.**

# === OkHttp (consumer rules bundled, safety net) ===
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# === Room (consumer rules bundled, safety net) ===
-keep class * extends androidx.room.RoomDatabase { *; }

# === Hilt / Dagger (consumer rules bundled, safety net) ===
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }

# === Kable BLE (no consumer rules) ===
-keep class com.juul.kable.** { public *; }
-dontwarn com.juul.kable.**

# === SkateLab models (serialized) ===
-keep class ru.skatelab.shared.models.** { *; }
-keep class ru.skatelab.shared.api.** { *; }
-keep class ru.skatelab.shared.auth.** { *; }

# === Protobuf (existing) ===
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    *** dynamicMethod(com.google.protobuf.GeneratedMessageLite$MethodToInvoke, java.lang.Object, java.lang.Object);
}
-keep class ru.skatelab.capture.proto.** { *; }

# === Kotlin coroutines (consumer rules bundled, safety net) ===
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembers class kotlinx.coroutines.** {
    volatile <fields>;
}

# === General Android ===
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# === R8 diagnostics (CI review) ===
-printconfiguration build/outputs/mapping/release-configuration.txt
-printseeds build/outputs/mapping/release-seeds.txt
-printusage build/outputs/mapping/release-usage.txt
```

---

## 6. Revised Network Security Config (Replacing Spec Section 3.2)

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Production: pin API certificate with backup for rotation -->
    <domain-config cleartextTrafficPermitted="false">
        <domain includeSubdomains="true">api.skatelab.com</domain>
        <pin-set expiration="2028-12-31">
            <!-- Primary: current production certificate SPKI hash -->
            <pin digest="SHA-256">PRODUCTION_PIN_BASE64_HERE</pin>
            <!-- Backup: different CA key for rotation (pre-pinned) -->
            <pin digest="SHA-256">BACKUP_PIN_BASE64_HERE</pin>
        </pin-set>
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </domain-config>

    <!-- Debug: trust user-added CAs for Charles/proxy tools -->
    <debug-overrides>
        <trust-anchors>
            <certificates src="system"/>
            <certificates src="user"/>
        </trust-anchors>
    </debug-overrides>
</network-security-config>
```

**Pin extraction:**
```bash
openssl s_client -connect api.skatelab.com:443 2>/dev/null | \
  openssl x509 -pubkey -noout | \
  openssl pkey -pubin -outform der 2>/dev/null | \
  openssl dgst -sha256 -binary | openssl base64
```

**Rotation procedure:** Pre-pin backup CA key. On rotation, new cert from backup CA works immediately. Push app update with new primary pin + new backup pin.

---

## 7. Accessibility: Key Patterns for SkateLab

### Decorative vs Meaningful Icons

| Element | contentDescription | Reason |
|---------|-------------------|--------|
| Icon in `ListItem` (BLE, info, logout) | `null` | Correct — `headlineContent` provides label |
| ProcessingScreen error icon | Needs description | Standalone, no text label nearby |
| Skeleton toggle button | `stringResource(R.string.show_skeleton)` | Interactive, no text label |
| Back arrow | `stringResource(R.string.nav_back)` | Interactive, no text label |

### Custom Composable Semantics

```kotlin
// SkeletonOverlay — decorative canvas
SkeletonOverlay(
    modifier = Modifier.clearAndSetSemantics {
        contentDescription = context.getString(R.string.skeleton_overlay_desc)
        role = Role.Image
    }
)

// Vico IMU chart — informative visualization
CartesianChartHost(
    modifier = Modifier.semantics(mergeDescendants = true) {
        contentDescription = "Angular velocity. Left peak $leftPeak, right peak $rightPeak"
        role = Role.Image
    }
)

// Loading state
Box(modifier = Modifier.semantics(mergeDescendants = true) {
    contentDescription = context.getString(R.string.loading)
    role = Role.ProgressIndicator
}) { CircularProgressIndicator() }

// Progress with value
LinearProgressIndicator(
    modifier = Modifier.semantics {
        progressBarRangeInfo = ProgressBarRangeInfo(
            current = state.percent, range = 0f..1f
        )
    }
)

// Error announcement
Column(modifier = Modifier.semantics {
    liveRegion = LiveRegion.Polite
    contentDescription = error.asString()
}) { /* error UI */ }
```

### BleScanStatus Enum (New Pattern)

```kotlin
enum class BleScanStatus {
    IDLE,
    RESETTING_LEFT, RESETTING_RIGHT,
    RESET_OK_LEFT, RESET_OK_RIGHT,
    RESET_FAILED,
    CALIBRATING_LEFT, CALIBRATING_RIGHT,
    CALIBRATION_OK_LEFT, CALIBRATION_OK_RIGHT,
    CALIBRATION_FAILED
}
// Composable maps BleScanStatus → stringResource(R.string.ble_status_resetting_left)
```

### CI Accessibility Testing

```kotlin
@get:Rule
val composeTestRule = createAndroidComposeRule<MainActivity>()

@Test
fun screenHasNoAccessibilityIssues() {
    composeTestRule.setContent { ProfileScreen(onLogout = {}) }
    composeTestRule.enableAccessibilityChecks()
    composeTestRule.onRoot().tryPerformAccessibilityChecks()
}
```

Requires dependency: `androidTestImplementation("androidx.compose.ui:ui-test-junit4-accessibility:1.8.2")`

---

## 8. BleScanViewModel: Status String Refactoring

Current code in `BleScanViewModel.kt` (lines 83-105):
```kotlin
_factoryResetStatus.value = "Сброс ${sensorId.name.lowercase()}..."
_factoryResetStatus.value = "Сброс ${sensorId.name.lowercase()} OK"
_factoryResetStatus.value = "Ошибка сброса: ${result.exceptionOrNull()?.message}"
_factoryResetStatus.value = "Калибровка ACC ${sensorId.name.lowercase()}... Датчик горизонтально!"
```

**Problem:** Russian hardcoded strings in ViewModel. Not errors (AppError doesn't apply). These are UI status labels.

**Fix:** Replace `StateFlow<String>` with `StateFlow<BleScanStatus?>` and map to `stringResource()` in the Composable.

This pattern should be applied to any ViewModel that exposes user-facing strings that aren't errors:
- `BleScanViewModel._factoryResetStatus` → `StateFlow<BleScanStatus?>`
- `RecordingScreen` reconnect status → `StateFlow<ReconnectStatus?>`

---

## 9. Timing Estimates

| Phase | Sequential | Parallelized | Speedup |
|-------|-----------|-------------|---------|
| Phase 1: Foundation | 30 min | 30 min | 1x (must be sequential) |
| Phase 2: i18n | 150 min | 45 min | 3.3x (5 agents) |
| Phase 2: A11y | 120 min | 60 min | 2x (70% parallel with i18n) |
| Phase 2: Security | 120 min | 45 min | 2.7x (4 tasks parallel) |
| Phase 2: Release verification | 30 min | 30 min | 1x (sequential gate) |
| **Total** | **~450 min (7.5h)** | **~210 min (3.5h)** | **2.1x** |

---

## 10. Spec Amendments Required

1. **Section 3.1 (ProGuard):** Replace `-keep class io.ktor.** { *; }` with narrow keeps from section 5 of this report
2. **Section 3.2 (NSC):** Add `cleartextTrafficPermitted="false"`, `expiration` on `<pin-set>`, system certs in `<debug-overrides>` from section 6
3. **Section 1.5 (ViewModel String Policy):** Add `BleScanStatus` enum pattern for non-error status strings from section 8
4. **Section 2.2 (Accessibility Fixes):** Add `enableAccessibilityChecks()` CI testing from section 7
5. **Section 2.3 (Semantic Patterns):** Replace spec examples with production patterns from section 7
6. **Add new section:** BleScanViewModel status string refactoring (section 8)

---

## Research Sources

### i18n
- Compose Multiplatform resources: https://kotlinlang.org/docs/multiplatform/compose-multiplatform-resources-usage.html
- Compose localization guide: https://kotlinlang.org/docs/multiplatform/compose-localize-strings.html
- UIText Compose (ViewModel antipattern): https://github.com/radusalagean/ui-text-compose
- Android Locale antipattern: https://medium.com/androiddevelopers/locale-changes-and-the-androidviewmodel-antipattern-84eb677660d9
- arrow-errors KMP hierarchy: https://github.com/blackarrows-apps/arrow-errors
- CMP-8934 (resource key readability): https://youtrack.jetbrains.com/projects/CMP/issues/CMP-8934

### Accessibility
- Compose accessibility testing: https://developer.android.com/develop/ui/compose/accessibility/testing
- Compose semantics: https://developer.android.com/develop/ui/compose/accessibility/semantics
- CVS Health Compose a11y techniques: https://github.com/cvs-health/android-compose-accessibility-techniques
- semantics vs clearAndSetSemantics: https://dladukedev.com/articles/002_semanics_vs_clearandsetsemantics
- Maestro a11y testing: https://grantisom.com/2023/07/19/accessibility-testing-in.html
- ui-test-junit4-accessibility: https://mvnrepository.com/artifact/androidx.compose.ui/ui-test-junit4-accessibility/1.8.2

### Security
- Android R8 keep rules blog: https://android-developers.googleblog.com/2025/01/configure-and-troubleshoot-r8-keep-rules.html
- kotlinx.serialization R8 rules: https://github.com/Kotlin/kotlinx.serialization/blob/master/rules/common.pro
- Now in Android baseline profiles: https://github.com/android/nowinandroid
- Diffuse (APK size diff): https://github.com/JakeWharton/diffuse
- Android NSC docs: https://developer.android.com/training/articles/security-config
