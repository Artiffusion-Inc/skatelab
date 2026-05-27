# KMP Development Skill — Design Spec

> Date: 2026-05-27
> Status: Draft

## Problem

10 Android-only skills deleted. No KMP skill exists on marketplace covering our stack. Generic KMP skills miss Kable BLE, multiplatform-settings, CameraX, WorkManager in KMP context. Need one authoritative skill matching our architecture.

## Scope

Single skill `kmp-development` covering Kotlin Multiplatform development for SkateLab mobile app. Organized like `impeccable` — entry SKILL.md + reference/ directory with sub-topics.

**In scope:** commonMain shared code, expect/actual boundaries, Android platform (Compose M3, Hilt, CameraX, Room, Kable BLE, WorkManager), iOS platform (SwiftUI interop, Keychain), Ktor 3.x, multiplatform-settings, coroutines/Flow, Clean Architecture, testing.

**Out of scope:** Backend (FastAPI), ML pipeline, frontend (Next.js), deployment/CI, design system (covered by `impeccable` and `platform-design`).

## Architecture Reference

```
mobile/
├── shared/                          # KMP shared module
│   └── src/
│       ├── commonMain/              # Business logic (API, auth, models, VMs)
│       ├── commonTest/              # Shared tests
│       ├── androidMain/             # Android expect/actual
│       └── iosMain/                # iOS expect/actual
├── androidApp/                      # Android app (Compose M3, Hilt, CameraX)
└── iosApp/                          # iOS app (SwiftUI, planned)
```

**Key stack:** Ktor 3.1.3, kotlinx-serialization 1.8.1, kotlinx-coroutines 1.10.2, multiplatform-settings 1.3.0, Compose BOM 2025.05.01, Hilt (KSP), Room, Kable (BLE), CameraX, Media3 ExoPlayer, WorkManager.

## Skill Structure

```
kmp-development/
├── SKILL.md                          # Entry point, routing table, shared laws
├── reference/
│   ├── shared-code.md                # Ktor client, serialization, ViewModels, Flow, coroutines
│   ├── expect-actual.md              # Platform boundaries, source sets, when to share vs split
│   ├── android-ui.md                 # Compose M3, Hilt DI, navigation, CameraX, Media3
│   ├── ios-ui.md                     # SwiftUI interop, SKIE, shared framework, Keychain
│   ├── platform-apis.md              # Kable BLE, CameraX, sensors, WorkManager
│   ├── data-layer.md                 # Room, multiplatform-settings, repository, offline-first
│   ├── error-handling.md             # Sealed error hierarchy, error propagation, Result types
│   ├── testing.md                    # commonTest, fakes-first, Mokkery, MockEngine, KMP patterns
│   └── gradle.md                     # Version catalog, convention plugins, KMP source sets
```

## SKILL.md — Entry Point

### Frontmatter

```yaml
name: kmp-development
description: Use when developing Kotlin Multiplatform apps — shared business logic in commonMain, platform UI (Android Compose M3 + Hilt, iOS SwiftUI), Ktor 3.x networking, expect/actual boundaries, Kable BLE, Room KMP, multiplatform-settings, CameraX, WorkManager, Mokkery testing, offline-first patterns. Trigger on KMP, Kotlin Multiplatform, shared module, commonMain, expect/actual, platform-specific code, KMP project structure, Kable, Hilt ViewModel, Compose navigation, SKIE interop. NOT for backend-only or frontend-only tasks.
argument-hint: "[topic] [target]"
user-invocable: true
```

### Routing Table

| Command | Target | Reference |
|---|---|---|
| `shared` | Networking, auth, ViewModels, Flow, coroutines | `reference/shared-code.md` |
| `platform` | expect/actual, source sets | `reference/expect-actual.md` |
| `android` | Compose, Hilt, navigation, CameraX, Room | `reference/android-ui.md` |
| `ios` | SwiftUI, SKIE, framework, Keychain | `reference/ios-ui.md` |
| `device` | BLE (Kable), sensors, WorkManager | `reference/platform-apis.md` |
| `data` | Room, settings, repository, offline-first | `reference/data-layer.md` |
| `error` | Sealed errors, Result types, propagation | `reference/error-handling.md` |
| `test` | Fakes, Mokkery, MockEngine, KMP patterns | `reference/testing.md` |
| `gradle` | Build config, dependencies | `reference/gradle.md` |

**Routing rules:**

1. No topic argument → read full SKILL.md + shared-code.md (default entry)
2. Multiple topics → load each reference sequentially, never skip
3. `android` + `device` overlap (CameraX, WorkManager) → `device` for API details, `android` for UI/wiring
4. `shared` + `error` overlap (error propagation) → `error` for hierarchy design, `shared` for flow wiring
5. `test` always last — testing patterns depend on code structure from other references

### Shared Laws

1. **commonMain first** — Code goes in commonMain unless platform forces otherwise. `expect/actual` is the escape hatch, not the default.
2. **Thin actuals** — `actual` implementations delegate to platform APIs, contain zero business logic. Extract shared logic to commonMain when actuals grow complex.
3. **Single source of truth** — Each concept has one canonical location. Types in `shared/src/commonMain`, platform wiring in `androidMain`/`iosMain`. Never duplicate across source sets.
4. **Test in commonTest** — Write tests in `commonTest` with `kotlin.test`. Platform-specific test in `androidTest`/`iosTest` only when testing platform API integration.
5. **Hilt for Android, no DI in shared** — Hilt lives in `androidApp`. `shared` module has zero DI framework dependency. Platform provides dependencies through factory functions.
6. **Repository in shared, DB in platform** — Repository interfaces in `commonMain`, Room/SQLDelight implementations in `androidMain`. iOS uses Keychain + UserDefaults via `multiplatform-settings`.
7. **Structured concurrency** — Use `viewModelScope` / `CoroutineScope` tied to lifecycle. Never `GlobalScope`. Cancel in `onCleared` / `deinit`. Use `SupervisorJob` for independent child coroutines.
8. **Sealed error hierarchy** — Domain errors as sealed interfaces in `commonMain`. No platform exceptions leak across boundaries. Every error type maps to a user-facing string, never raw exception messages.
9. **Immutable UiState** — `UiState` is a `data class` or `value class`. Mutations via `copy()`. Events via `SharedFlow<UiAction>`. No mutable fields in state holders.
10. **No platform types in commonMain** — `commonMain` never references `android.*`, `javax.*`, `ios.*`. Platform types stay behind `expect/actual` or factory functions.

## Reference Files — Content Outline

### reference/shared-code.md

- Ktor 3.x client setup (OkHttp engine Android, Darwin engine iOS)
- Auth interceptors (token refresh, 401 handling)
- kotlinx-serialization (Json config, @Serializable)
- ViewModels in shared (`StateFlow` + `SharedFlow` for events)
- Coroutines: `Dispatchers.Default` for CPU, `Dispatchers.IO` for network, `Dispatchers.Main` for UI
- Structured concurrency: `viewModelScope`, `SupervisorJob`, cancellation propagation
- Flow operators: `stateIn`, `shareIn`, `combine` for reactive streams
- Error propagation chain: DataSource → Repository → UseCase → ViewModel

### reference/expect-actual.md

- Decision framework: interface vs expect/actual (prefer interface for stateless, expect/actual for platform API access)
- Source set hierarchy: commonMain → [jvmAndroid → androidMain], [native → appleMain → iosMain]
- When to create intermediate source sets (jvmAndroid for shared JVM between Android + potential desktop)
- Thin actual pattern: actual delegates to platform, no business logic
- Common mistakes: putting logic in actual, wrong source set, circular dependencies

### reference/android-ui.md

- Compose M3 theming (our OKLCH palette, Inter font)
- Hilt DI wiring (Application → @HiltAndroidApp → @HiltViewModel → Repository)
- Navigation Compose with type-safe routes
- CameraX video capture pipeline (ProcessCameraProvider, VideoCapture, MediaStore output)
- Media3 ExoPlayer for playback
- Screen architecture: ViewModel + UiState + UiAction + UiEffect pattern
- Hilt + WorkManager integration: `HiltWorkerFactory`, `@HiltWorker` for injected workers

### reference/ios-ui.md

- SwiftUI interop with shared KMP framework
- XCFramework consumption via SPM (spm4Kmp plugin for automated publishing)
- Keychain integration via multiplatform-settings
- SKIE: primary interop tool — `Flow.asAsyncSequence()`, `@NativeCoroutines`, `@Sketch`
- SKIE vs KMP-NativeCoroutines vs Swift Export (SKIE recommended: maintained, breadth of features)
- Shared ViewModel consumption from SwiftUI: lifecycle scoping via `ObservableObject`
- ViewModel `deinit` must cancel `viewModelScope` — no leaked coroutines

### reference/platform-apis.md

- **Kable BLE**: connection lifecycle (`Peripheral` builder), characteristic read/write/notify, reconnection strategy, platform service UUIDs
- **CameraX**: ProcessCameraProvider binding, video capture, permission handling, lifecycle awareness
- **WorkManager**: background upload workers, constraints, chaining, `HiltWorkerFactory` integration (Android-only, iOS uses BGTaskScheduler)
- **Sensors**: IMU data flow via Kable characteristics (quaternion, accelerometer, gyroscope)
- **multiplatform-settings**: `Settings()` factory, `PlatformSettings` with `EncryptedSharedPreferences` (Android) / Keychain (iOS)

### reference/data-layer.md

- Room KMP: entities, DAOs, migrations, type converters
- multiplatform-settings: EncryptedSharedPreferences (Android), Keychain (iOS)
- Repository pattern: interface in commonMain, implementation per platform
- Offline-first strategy:
  - `SyncState` enum: `SYNCED`, `PENDING_UPLOAD`, `PENDING_DOWNLOAD`, `CONFLICT`
  - Server-wins conflict resolution (last-write-wins with server timestamp)
  - Event-driven sync: `SyncEvent` sealed class triggers sync on network restore
  - Dirty flag tracking per entity for incremental sync
- Token storage: multiplatform-settings with platform-specific encryption
- Room KMP migration path: commonMain DAOs work across platforms, `androidMain` provides `RoomDatabase` actual

### reference/error-handling.md

- Sealed error hierarchy in `commonMain`: `AppError` → `NetworkError`, `StorageError`, `AuthError`, `DeviceError`
- No platform exceptions cross boundaries — wrap in domain errors at `actual` layer
- `Result<T, AppError>` as return type for UseCases and Repositories
- Error-to-UiState mapping: each `AppError` subtype maps to user-facing Russian string
- Error propagation: `catch` at ViewModel → emit error state, never crash
- Logging boundary: platform actuals log raw exceptions before wrapping

### reference/testing.md

- commonTest with kotlin.test + kotlinx-coroutines-test
- Turbine for Flow assertions
- **Fakes-first strategy**: hand-written fakes for repositories and data sources (primary approach)
- **Mokkery** (not mockative/MockK) for KMP mocking — single mock framework across source sets
- **Ktor MockEngine** (not MockWebServer) for commonTest networking — no JVM dependency
- Platform test runners: androidTest, iosTest
- Integration tests: Room in-memory DB, Ktor test server
- Shared ViewModel test pattern: `TestDispatcher`, `Turbine`, state snapshot assertions
- Fake repository pattern: `FakeSessionRepository`, `FakeSettingsRepository` in commonTest

### reference/gradle.md

- libs.versions.toml: our current versions (Kotlin 2.1.21, Ktor 3.1.3, etc.)
- KMP source set configuration in shared/build.gradle.kts
- Convention plugins pattern (android, kmp, compose)
- Debug vs release build variants
- ProGuard/R8 rules for Android
- SKIE Gradle plugin configuration
- KSP vs KAPT (use KSP exclusively for Hilt + Room)

## Marketplace Skills Integration

### Install (complementary, no duplication)

| Skill | Stars | Covers | Why install |
|-------|-------|--------|-------------|
| `rcosteira79/android-skills` | 62 | Ktor client, MockEngine testing, error mapping at repository boundary, expect/actual decision framework | Best Ktor KMP reference. RIGHT/WRONG examples. Stack match (Hilt, Ktor, MockEngine) |
| `trancee/MeshLink` skie | 0 | SKIE exhaustive enums, Flow→AsyncSequence, suspend→async, Swift bundling, migration, configuration | Most comprehensive SKIE reference. Covers all interop patterns |
| `sorunokoe/swift-kmp-skill` | 4 | KMP→Swift bridge layer architecture, type mapping, error boundary, review checklist | Hard rules for KMP imports confinement. Pairs with MeshLink SKIE skill |

### Previously identified (keep)

| Skill | Covers | Why keep external |
|---|---|---|
| `mmiani/kotlin-project-feature-implementation` | Feature workflow (inspect→plan→impl→check) | Process skill, not stack-specific |
| `mmiani/kotlin-project-code-review` | 24-point review checklist | Review methodology |
| `ghaylansaada/kmp-background-job` | WorkManager + BGTaskScheduler cross-platform | Specialized deep-dive |
| `chrisbanes/kotlin-multiplatform-expect-actual` | expect/actual decision framework (670★) | Authoritative, concise |

### Absorbed into kmp-development reference files

Content from these skills synthesized into our own reference files (not installed separately):

| Topic | Sources | Target file |
|-------|---------|-------------|
| Mokkery + fakes-first testing | Strakk `kmp-testing`, NutriSport `gen-test`, blackjack `mokkery` | `reference/testing.md` |
| Ktor MockEngine patterns | cc-mobile `kmm-testing`, Masum-MSNR `kmp-testing`, rcosteira79 `kmp-ktor` | `reference/testing.md` + `reference/shared-code.md` |
| multiplatform-settings | cc-mobile `multiplatform-settings` | `reference/data-layer.md` |
| Offline-first sync (adapted for Room) | Masum-MSNR `kmp-offline-sync` | `reference/data-layer.md` |
| Sealed error hierarchy | rcosteira79 `kmp-ktor`, Masum-MSNR | `reference/error-handling.md` |
| SKIE interop patterns | MeshLink `skie`, sorunokoe `swift-kmp` | `reference/ios-ui.md` |
| iOS interop diagnostics | game-deals `kmp-ios-interop-fixer` | `reference/ios-ui.md` |
| Module architecture | game-deals `kmp-shared-module-architect`, Masum-MSNR | `reference/expect-actual.md` |

### No marketplace coverage (write from scratch)

| Gap | Reason |
|-----|--------|
| Kable BLE patterns | No skill covers BLE for KMP |
| Room KMP patterns | All marketplace skills use SQLDelight, not Room |
| Hilt + WorkManager integration | No skill covers `@HiltWorker` / `HiltWorkerFactory` |

`kmp-development` references installed skills where they provide more depth, doesn't duplicate their content.

## Design Decisions

1. **One skill, not many** — Unlike deleted Android skills (10 overlapping), single entry point with reference/ files reduces discovery cost and duplication.
2. **Project-specific, not generic** — References our stack versions, our architecture, our patterns (not "KMP in general").
3. **Hilt in androidApp only** — shared module stays DI-framework-free. Koin is NOT used. This is a deliberate architectural choice.
4. **multiplatform-settings over DataStore** — We use multiplatform-settings with platform-specific encryption, not DataStore.
5. **Kable over platform BLE APIs** — Single abstraction for WT901 sensor communication.
6. **Room (not SQLDelight)** — Our DB is Room with KSP. SQLDelight mentioned only as migration path consideration.
7. **SKIE for iOS interop** — Primary tool for Flow→AsyncSequence, @NativeCoroutines. KMP-NativeCoroutines deprecated path. Swift Export immature.
8. **Mokkery for mocking** — Single mock framework across all source sets. Not mockative (limited), not MockK (Android-only).
9. **Ktor MockEngine for tests** — Runs in commonTest, no JVM dependency. MockWebServer is JVM-only.
10. **Fakes-first testing** — Hand-written fakes for repositories/data sources. Mokkery only for complex or rarely-used dependencies.
11. **Sealed error hierarchy** — Domain errors as sealed interfaces in commonMain. No platform exceptions leak across boundaries.
12. **Offline-first with server-wins** — SyncState enum, event-driven sync, server-wins conflict resolution.

## Resolved Decisions

1. **Scope**: User scope (`~/.agents/skills/kmp-development/`) — available across all projects, not tied to SkateLab repo.
2. **iOS content**: Include now — theme files exist, SwiftUI reference written for future use.
3. **Device APIs**: Generic CameraX/Kable patterns, no project-specific WT901 code.
4. **Design system**: Cross-reference `platform-design` and `impeccable` skills for OKLCH palette, Inter font, design tokens. Do not duplicate.

## Research Synthesis

Five specialized agents reviewed the spec and researched the marketplace, GitHub, and web for improvements. Key findings incorporated:

**Agent 1 — Structure & Laws:** Added 4 new shared laws (7–10: structured concurrency, sealed errors, immutable UiState, no platform types in commonMain). Removed arbitrary 20-line threshold from Law 2. Identified 3 missing reference files (error-handling.md, coroutines merged into shared-code.md, navigation merged into android-ui.md).

**Agent 2 — Platform APIs:** Kable patterns expanded (connection lifecycle, characteristic patterns, reconnection). CameraX patterns (lifecycle, permission handling). WorkManager+Hilt integration pattern (`HiltWorkerFactory`, `@HiltWorker`). multiplatform-settings encryption detail (EncryptedSharedPreferences / Keychain).

**Agent 3 — iOS Interop:** SKIE identified as primary interop tool (not KMP-NativeCoroutines, not Swift Export). spm4Kmp plugin for SPM publishing. ViewModel lifecycle scoping in SwiftUI (`ObservableObject`, `deinit` cancellation).

**Agent 4 — Structure & CSO:** Merged 8→9 reference files (added error-handling.md). Enhanced CSO description with stack-specific keywords (Kable, Hilt ViewModel, Compose navigation, SKIE). Added routing rules to prevent reference-load ordering issues. Proposed TDD baseline scenarios for skill validation.

**Agent 5 — Testing & Data:** Corrected mockative→Mokkery, MockWebServer→Ktor MockEngine. Added fakes-first testing strategy. Expanded offline-first from one line to full pattern (SyncState, server-wins, event-driven sync). Room KMP commonTest pattern added.