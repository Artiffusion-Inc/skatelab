# Mobile

Kotlin Multiplatform shared networking/auth/state, native Android Compose UI, SwiftUI iOS shell.

## Boundaries

- `shared/src/commonMain/` — platform-neutral API, auth, models, repositories, state.
- `shared/src/androidMain/`, `iosMain/` — platform implementations.
- `androidApp/` — Compose UI, Hilt, CameraX, BLE, Room, WorkManager, Media3.
- `iosApp/` — SwiftUI application and platform theme.

Android architecture: presentation -> domain interfaces/use cases -> data implementations.

## Rules

- Keep `commonMain` free of Android/iOS APIs; use expect/actual or injected interfaces.
- Ktor non-success responses must become typed errors; never silently return success-shaped data.
- Recording synchronizes CameraX video and WT901 BLE samples. Preserve timestamps and upload retry semantics.
- Use visible text for Maestro selectors; Compose `testTag` is not reliable through UI Automator.
- Never store live credentials in tests or instructions.
- Confirm `BUILD SUCCESSFUL` and APK checksum before installation or distribution.

## Verify

```bash
cd mobile
./gradlew ktlintCheck
./gradlew :shared:allTests
./gradlew :androidApp:testDebugUnitTest
./gradlew :androidApp:assembleDebug
md5sum androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

Use containerized emulator scripts in `mobile/e2e/`; avoid host ADB when container is active.
