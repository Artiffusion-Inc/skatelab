# Mobile Quality Hardening — Design Spec

Date: 2026-05-27
Branch: TBD
Scope: i18n, accessibility, security, performance, sealed error hierarchy
Related: `docs/specs/2026-05-22-mobile-audit-fixes-design.md` (bug fixes — already planned)

## Overview

KMP audit revealed quality gaps beyond bug fixes: 74 hardcoded Russian strings, 6 null content descriptions, minimal ProGuard rules, no network security config, raw exception messages in UiState, and `fallbackToDestructiveMigration` without debug guard. This spec hardens the Android app for production quality while preparing shared module for future iOS localization.

**Not in scope:** Bug fixes from `mobile-audit-fixes-design.md` (auth, SSE, BLE, upload). iOS UI implementation (separate spec).

## Wave 0 — Core: Sealed AppError + fallbackToDestructiveMigration

### 0.1 — Sealed AppError Hierarchy

**Problem:** All 3 shared ViewModels use `UiState.Error(message: String)` / `ProcessingUiState.Failed(message: String)` with raw `e.message ?: "fallback"`. Raw exception messages (English, technical) leak to users. No type information for UI to show different UX per error kind. Cannot localize.

**Fix:** Add sealed `AppError` interface in commonMain. ViewModels map exceptions to `AppError`. `UiState.Error` carries `AppError` instead of `String`.

```kotlin
// commonMain/models/AppError.kt
sealed interface AppError {
    val messageKey: String

    data class Network(override val messageKey: String = "error_network") : AppError
    data class Auth(override val messageKey: String = "error_auth") : AppError
    data class NotFound(override val messageKey: String = "error_not_found") : AppError
    data class Server(override val messageKey: String = "error_server") : AppError
    data class Timeout(override val messageKey: String = "error_timeout") : AppError
    data class Unknown(override val messageKey: String = "error_unknown") : AppError
}
```

```kotlin
// commonMain/utils/ExceptionMapping.kt
import io.ktor.client.network.sockets.SocketTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import kotlinx.io.IOException
import io.ktor.http.HttpStatusCode

fun Throwable.toAppError(): AppError = when (this) {
    is SocketTimeoutException, is HttpRequestTimeoutException -> AppError.Timeout()
    is IOException -> AppError.Network()
    else -> AppError.Unknown()
}

fun HttpStatusCode.toAppError(): AppError = when (value) {
    401 -> AppError.Auth()
    404 -> AppError.NotFound()
    in 500..599 -> AppError.Server()
    else -> AppError.Unknown()
}
```

**ViewModel changes:**

```kotlin
// SessionsViewModel — before
data class Error(val message: String) : SessionsUiState
// SessionsViewModel — after
data class Error(val error: AppError) : SessionsUiState

// Usage
catch (e: Exception) {
    _uiState.value = SessionsUiState.Error(e.toAppError())
}
```

Same pattern for `AuthUiState.Error`, `ProcessingUiState.Failed`.

**Android side:** Extension function renders `AppError` as localized string:

```kotlin
// androidApp/utils/AppErrorExt.kt
@Composable
fun AppError.asString(): String = stringResource(
    when (this) {
        is AppError.Network -> R.string.error_network
        is AppError.Auth -> R.string.error_auth
        is AppError.NotFound -> R.string.error_not_found
        is AppError.Server -> R.string.error_server
        is AppError.Timeout -> R.string.error_timeout
        is AppError.Unknown -> R.string.error_unknown
    }
)
```

**Test:** `AppErrorTest` (commonTest) — exception mapping, HTTP status mapping. `SessionsViewModelTest` — errors carry `AppError`, not `String`.

### 0.2 — fallbackToDestructiveMigration Debug Guard

**Problem:** `DatabaseModule.kt:25` calls `fallbackToDestructiveMigration(true)` unconditionally. In release builds, Room silently drops all user data on schema migration.

**Fix:**

```kotlin
// DatabaseModule.kt
val builder = Room.databaseBuilder(context, AppDatabase::class.java, "skatelab.db")
if (BuildConfig.DEBUG) {
    builder.fallbackToDestructiveMigration(true)
}
builder.build()
```

In release, Room throws `IllegalStateException` on migration mismatch — better than silent data loss. Add migration path for future schema changes (version 1→2).

**Test:** `AppDatabaseTest` — verify destructive migration only in debug.

---

## Wave 1 — i18n: Extract Hardcoded Strings

### 1.1 — Current State

- `values/strings.xml` — ~30 keys, all Russian (should be default English)
- `values-ru/` — **directory missing** (Russian strings are in default)
- 74 hardcoded Russian strings in Kotlin composables and ViewModels
- No `values-en/strings.xml`

### 1.2 — Target Structure

```
res/
├── values/
│   └── strings.xml          # English (default) — system uses this if locale not matched
├── values-ru/
│   └── strings.xml          # Russian — primary audience
```

**Why English as default?** Android loads `values/strings.xml` when no locale-specific match exists. English as default ensures the app works on any device. Russian as `values-ru/` is the primary translation.

### 1.3 — String Resource Categories

| Category | Prefix | Example keys | Count (est.) |
|----------|--------|-------------|-------------|
| Errors | `error_` | `error_network`, `error_auth`, `error_timeout` | ~10 |
| BLE scan | `ble_` | `ble_scan_title`, `ble_connected`, `ble_reset_left` | ~12 |
| Calibration | `calibration_` | `calibration_title`, `calibration_done` | ~8 |
| Recording | `recording_` | `recording_active`, `recording_start` | ~8 |
| Session | `session_` | `session_list_title`, `session_detail_title` | ~10 |
| Export | `export_` | `export_title`, `export_done` | ~6 |
| Profile | `profile_` | `profile_title`, `profile_logout` | ~6 |
| IMU | `imu_` | `imu_left`, `imu_right`, `imu_chart_desc` | ~8 |
| Processing | `processing_` | `processing_queuing`, `processing_cancel` | ~6 |
| General | `general_` | `general_retry`, `general_cancel`, `general_ok` | ~6 |
| **Total** | | | **~80** |

> **Note:** The ~80 count is estimated. Exact count determined during extraction. Each hardcoded string becomes one `<string>` element plus its English counterpart.

### 1.4 — Extraction Rules

1. **Extract all user-visible strings** from composables → `stringResource(R.string.key)`
2. **Extract error strings from ViewModels** → use `AppError.messageKey` (Wave 0 dependency)
3. **Do NOT extract:** log messages (`Log.d`, `Log.w`), debug format strings (`"Л: пик ${leftPeak}$unit"` — keep in code but use format key)
4. **Format strings** use `stringResource(R.string.key, arg1, arg2)` — e.g., `"RSSI: %d"` → `<string name="ble_rssi">RSSI: %1$d</string>`
5. **Plurals** — use `<plurals>` for count-based strings if needed (not anticipated for MVP)

### 1.5 — ViewModel String Policy

ViewModels **must not** contain user-facing strings. All error messages go through `AppError`. All UI labels come from `stringResource()`. Status strings like `"Сброс лев..."` in `BleScanViewModel` move to `StateFlow<AppError>` or `StateFlow<Int>` (resource ID).

Exception: debug/log strings stay hardcoded.

### 1.6 — Hardcoded Strings Inventory (top files)

| File | Hardcoded strings | Priority |
|------|-------------------|----------|
| `presentation/ble/BleScanScreen.kt` | ~8 | High |
| `presentation/ble/BleScanViewModel.kt` | ~6 | High (ViewModel — must refactor) |
| `presentation/sessiondetail/SessionDetailScreen.kt` | ~8 | High |
| `presentation/recording/RecordingScreen.kt` | ~4 | Medium |
| `ui/profile/MoreScreen.kt` | ~3 | Medium |
| `ui/profile/ProfileScreen.kt` | ~2 | Low |
| `ui/camera/CameraScreen.kt` | ~2 | Low |

**Total: ~74 strings across 10+ files**

---

## Wave 2 — Accessibility

### 2.1 — Current State

- 6 `contentDescription = null` — icons invisible to TalkBack
- No `Modifier.semantics {}` on custom composables (charts, skeleton overlay)
- No font scaling testing
- Touch target sizes not verified

### 2.2 — Fixes

**contentDescription:**

| Screen | Element | Current | Fix |
|--------|---------|---------|-----|
| MoreScreen | 3 icons | `null` | `stringResource(R.string.icon_desc_X)` |
| ProfileScreen | Avatar + Save | `null` / hardcoded | `stringResource(R.string.avatar_desc)` |
| SessionDetailScreen | Back arrow | hardcoded `"Назад"` | `stringResource(R.string.nav_back)` |

**Custom composables:**

- `Vico` IMU charts — add `Modifier.semantics { contentDescription = stringResource(R.string.imu_chart_desc, leftLabel, rightLabel); role = Role.Image }`
- `SkeletonOverlay` — add semantics for skeleton visualization
- `ProcessingScreen` progress indicator — add semantics for progress percentage

**Touch targets:**

- Audit all `IconButton` instances — ensure minimum 48dp touch target via padding or `minimumInteractiveComponentSize()`
- Audit `BottomNavigation` tab items — Material 3 defaults should be compliant

**Font scaling:**

- Verify layout with `fontScale = 1.5` and `2.0` in emulator
- Not a blocker for MVP, but document any issues found

### 2.3 — Semantic Patterns

```kotlin
// Chart with meaningful description
VicoChart(
    modifier = Modifier.semantics {
        contentDescription = context.getString(R.string.imu_chart_desc, leftLabel, rightLabel)
        role = Role.Image
    }
)

// Loading state
if (state is SessionsUiState.Loading) {
    Box(
        modifier = Modifier.semantics {
            contentDescription = context.getString(R.string.loading)
            role = Role.ProgressIndicator
        }
    ) { CircularProgressIndicator() }
}

// Error state with announcement
LaunchedEffect(error) {
    accessibilityManager.performAccessibilityAction(
        AccessibilityEvent.TYPE_ANNOUNCEMENT,
        error.asString(context)
    )
}
```

---

## Wave 3 — Security + Performance

### 3.1 — ProGuard Rules Expansion

**Current:** Only protobuf keep rules (2 lines).

**Needed:**

```proguard
# === Ktor ===
-keep class io.ktor.** { *; }
-keep class kotlinx.serialization.** { *; }
-dontwarn io.ktor.**
-keepclassmembers class ** {
    @kotlinx.serialization.Serializable <init>(...);
}

# === Kable BLE ===
-keep class com.juul.kable.** { *; }

# === Room ===
-keep class * extends androidx.room.RoomDatabase { *; }
-keep @androidx.room.Entity class * { *; }
-keep class * extends androidx.room.Dao { *; }

# === Hilt ===
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }
-keep class * extends dagger.hilt.android.internal.managers.ViewComponentManager$FragmentContextWrapper { *; }

# === SkateLab models (serialized) ===
-keep class ru.skatelab.shared.models.** { *; }
-keep class ru.skatelab.shared.api.** { *; }
-keep class ru.skatelab.shared.auth.** { *; }

# === Protobuf (existing) ===
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    *** dynamicMethod(com.google.protobuf.GeneratedMessageLite$MethodToInvoke, java.lang.Object, java.lang.Object);
}
-keep class ru.skatelab.capture.proto.** { *; }
```

**Test:** Build release APK with `isMinifyEnabled = true` → run all instrumented tests on release build.

### 3.2 — Network Security Config

**File:** `res/xml/network_security_config.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Production: pin API certificate -->
    <domain-config>
        <domain includeSubdomains="true">api.skatelab.com</domain>
        <pin-set>
            <pin digest="SHA-256">PRODUCTION_PIN_BASE64</pin>
            <pin digest="SHA-256">BACKUP_PIN_BASE64</pin>
        </pin-set>
        <trust-anchors>
            <certificates src="system"/>
        </trust-anchors>
    </domain-config>

    <!-- Debug: trust user-added CAs for proxy tools -->
    <debug-overrides>
        <trust-anchors>
            <certificates src="user"/>
        </trust-anchors>
    </debug-overrides>
</network-security-config>
```

**Pin values:** Extract SHA-256 from production TLS certificate: `openssl s_client -connect api.skatelab.com:443 | openssl x509 -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | openssl base64`. Backup pin is a key rotation placeholder (different CA key, same authority). **Must be set before Play Store launch.**

**Manifest reference:** Add `android:networkSecurityConfig="@xml/network_security_config"` to `<application>`.

### 3.3 — API Key Safety Audit

Search codebase for hardcoded API keys, secrets, tokens. All must be in `BuildConfig` fields via `buildConfigField` from environment variables or CI secrets.

### 3.4 — Baseline Profiles (P2)

Add `baselineprofile` Gradle plugin to generate startup optimization profiles. Requires running on a physical device or emulator with user flows.

```kotlin
// build.gradle.kts (androidApp)
plugins {
    id("androidx.baselineprofile")
}

baselineProfile {
    downloadProfiles = true
}
```

Not blocking for MVP. Add after Play Store launch.

### 3.5 — APK Size Monitoring (P3)

Add size check to CI:

```yaml
# mobile-build.yml — add after APK build
- name: Check APK size
  run: |
    APK_SIZE=$(stat -c%s mobile/androidApp/build/outputs/apk/debug/*.apk)
    echo "APK size: $APK_SIZE bytes ($(( APK_SIZE / 1048576 )) MB)"
    if [ $APK_SIZE -gt 52428800 ]; then  # 50 MB
      echo "::warning::APK exceeds 50 MB"
    fi
```

Not blocking for MVP. Informational.

---

## iOS Outline (Preview)

Not in implementation scope. Reference for future spec.

| Component | Status | Effort | Dependency |
|-----------|--------|--------|------------|
| Xcode project | Not started | 2-3 days | Xcode on macOS |
| SKIE integration | Not configured | 1 day | shared module stable |
| SwiftUI screens (10+) | Not started | 3-4 weeks | Design system (exists in Swift) |
| Apple Developer Account | Not set up | 1 day | $99/year |
| Signing + Provisioning | Not started | 1 day | Apple Developer Account |
| TestFlight CI | Not started | 2-3 days | GitHub Actions macOS runner |
| iOS E2E (Maestro) | Deferred | 1-2 days | Maestro fix for Compose iOS |

**Key risk:** Kable BLE on iOS requires CoreBluetooth. CameraX has no iOS equivalent — iOS would use gallery photo picker or AVFoundation (separate effort). Shared ViewModels work via SKIE, but lifecycle management differs.

---

## Dependency Graph

```
Wave 0 (AppError + fallbackToDestructiveMigration)
  ↓ AppError.messageKey needed for i18n string resources
Wave 1 (i18n — extract strings, values-en/values-ru)
  ↓ String resources needed for accessibility descriptions
Wave 2 (Accessibility — contentDescription, semantics, touch targets)
  ↓ No hard dependency, but security is independent
Wave 3 (Security + Performance — ProGuard, network config, cert pinning)
```

Waves 2 and 3 are independent of each other and can run in parallel once Wave 1 completes.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| AppError refactoring breaks existing error handling in ViewModels | Medium | High | Incremental migration: add AppError alongside String, then switch; existing tests as safety net |
| ProGuard rules break release build | Medium | High | Test release APK on emulator after changes; keep debug builds unaffected |
| Certificate pinning blocks development (self-signed certs) | Low | Medium | `debug-overrides` allows user CAs; disable pinning in debug |
| i18n extraction misses strings (runtime crash) | Low | Medium | Lint `MissingTranslation` check in CI; manual QA pass |
| Baseline profiles wrong on first run | Low | Low | Not blocking for MVP; add post-launch |
| Accessibility semantics break layout | Low | Low | Semantics don't affect visual layout; only a11y tree |

---

## Out of Scope

- Bug fixes from `2026-05-22-mobile-audit-fixes-design.md` (auth, SSE, BLE, upload)
- iOS UI implementation
- Play Store publishing (signing config, launcher icon, screenshots, content rating, privacy policy)
- Email verification / password reset UI screens
- Session CRUD UI screens
- Metrics dashboard UI
