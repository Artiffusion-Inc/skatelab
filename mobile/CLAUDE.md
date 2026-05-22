# mobile/CLAUDE.md

## Overview

Kotlin Multiplatform app: shared logic (auth, API, models) + native UI per platform.
- **Android**: Jetpack Compose + Material 3 — реализовано
- **iOS**: SwiftUI — планируется в ближайшем будущем

Shared модуль avoids code duplication. UI нативный на каждой платформе. Design system единая с frontend.

## History

Flutter → native Kotlin (05-09) → KMP shared module (05-22). Camera2 removed early — recording via CameraX only.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Shared** | KMP, kotlinx-serialization, Ktor, kotlinx-datetime |
| **Android UI** | Jetpack Compose, Material 3, Navigation Compose |
| **iOS UI** | SwiftUI (planned) |
| **DI** | Hilt (KSP) |
| **Network** | Ktor (OkHttp Android, Darwin iOS) |
| **BLE** | Kable (WT901 IMU sensors) |
| **DB** | Room (Android, cached sessions + pending uploads) |
| **Camera** | CameraX (video recording) |
| **Video playback** | Media3 ExoPlayer |
| **Charts** | Vico (Compose + Material 3) |
| **Background** | WorkManager (chunked upload), Foreground Service (sensor recording) |
| **Protobuf** | protobuf-javalite (IMU data serialization) |
| **Testing** | kotlin-test, coroutines-test, MockK, Turbine, Mokkery (commonTest), Kover |
| **Lint** | ktlint |
| **Build** | Gradle + build-logic conventions, configuration cache, KSP isolation |

Min SDK 24, Target SDK 35, Compose BOM managed.

## Project Structure

```
mobile/
├── shared/                        # KMP shared module
│   └── src/
│       ├── commonMain/             # API client, auth, models (shared Android+iOS)
│       │   └── ru/skatelab/shared/
│       │       ├── api/            # SkateLabClient, AuthApi, SessionsApi, UploadsApi, UsersApi, ProcessApi
│       │       ├── auth/          # AuthRepository, TokenStorage (multiplatform-settings)
│       │       ├── models/        # TokenResponse, SessionResponse, UserResponse, etc.
│       │       └── state/         # AuthViewModel, SessionsViewModel, ProcessingViewModel
│       ├── commonTest/            # Shared tests (AuthApi, AuthRepository, Serialization)
│       ├── androidMain/           # Android-specific: OkHttp engine, AndroidTokenStorage
│       └── iosMain/               # iOS-specific: Darwin engine, IosTokenStorage
├── androidApp/                    # Android app (92 source files)
│   └── src/main/java/ru/skatelab/capture/
│       ├── App.kt                 # Hilt application
│       ├── MainActivity.kt
│       ├── di/                    # Hilt modules: AppModule, CameraModule, DatabaseModule
│       ├── navigation/            # Routes
│       ├── domain/                # Clean Architecture domain layer
│       │   ├── model/            # CalibrationData, CaptureSession, ImuSample, SensorInfo
│       │   ├── repository/       # BleRepository, CameraRepository, SessionRepository (interfaces)
│       │   ├── service/          # ImuCollector, Logger, SessionExporter, TimeSynchronizer (interfaces)
│       │   └── usecase/          # 12 use cases (Connect, Calibrate, Record, Export, etc.)
│       ├── data/                  # Implementations
│       │   ├── ble/              # BleManager, KableBleRepository, Wt901Parser, Wt901Commander
│       │   ├── camera/           # CameraXRecorder, CameraRepositoryImpl
│       │   ├── db/               # Room: AppDatabase, CachedSessionDao, PendingUploadDao
│       │   ├── export/           # ImuStreamWriter, ManifestBuilder, ZipExporter
│       │   ├── imu/              # ImuParser
│       │   ├── recording/        # ImuCollector (implementation)
│       │   ├── repository/       # SessionRepositoryImpl
│       │   ├── share/            # ShareManager
│       │   └── sync/             # TimeSyncManager, TimeSynchronizerImpl, PeriodicTimeSync
│       ├── presentation/          # Feature screens + ViewModels
│       │   ├── ble/              # BleScanScreen + ViewModel
│       │   ├── calibration/      # CalibrationScreen + ViewModel (Markley eigendecomposition)
│       │   ├── recording/        # RecordingScreen + ViewModel
│       │   ├── session/          # SessionListScreen + ViewModel
│       │   ├── sessiondetail/    # SessionDetailScreen + ViewModel (ExoPlayer + IMU charts)
│       │   ├── export/           # ExportScreen + ViewModel
│       │   └── theme/            # SkateLab theme (Inter Variable, OKLCH colors, unified design system)
│       ├── ui/                    # Android-specific UI components (auth, camera, profile, tabs)
│       ├── service/               # SensorRecordingService (foreground)
│       └── upload/                # ChunkedUploader, UploadScheduler, UploadWorker
├── proto/                         # Protobuf definitions
├── build-logic/                   # Gradle convention plugins
└── scripts/                      # Build scripts
```

## Architecture

Clean Architecture: **presentation** → **domain** → **data**

- domain/ содержит interfaces (repository, service) + models + use cases
- data/ содержит implementations
- presentation/ содержит Compose screens + ViewModels (StateFlow)

Shared module: API client + auth + models — переиспользуется Android и iOS.

## Key Flows

- **BLE**: Kable → Wt901Parser → ImuCollector → foreground service
- **Recording**: CameraX video + BLE IMU simultaneously, time-synced via TimeSynchronizerImpl
- **Upload**: ChunkedUploader → UploadWorker (WorkManager, retry on failure)
- **Calibration**: Markley eigendecomposition + tightened thresholds
- **Session viewer**: ExoPlayer video + Vico IMU charts + playhead sync

## Design System

Unified with frontend: OKLCH colors, Inter Variable font, same border-radius tokens. Style Dictionary generates CSS/Android/iOS tokens.

## Before Committing

1. **Lint**: `./gradlew ktlintCheck`
2. **Tests**: `./gradlew testDebugUnitTest`
3. **Build**: `./gradlew assembleDebug`