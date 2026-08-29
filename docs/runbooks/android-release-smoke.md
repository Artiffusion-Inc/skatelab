# Android release smoke runbook

Status: synthetic pilot runbook. Do not describe a build as hardware-validated until real WT901 sessions have been collected and labelled.

## 1. Build checks

Run from the repository root:

```bash
cd mobile
./gradlew ktlintCheck :shared:allTests :androidApp:testDebugUnitTest --no-daemon --max-workers=1
./gradlew :androidApp:assembleDebug --no-daemon --max-workers=1
sha256sum androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

The required result is `BUILD SUCCESSFUL`, followed by a checksum for the produced debug APK. The current Task 4 checkout reached Kotlin compilation, but the combined test/build command lost its Gradle daemon during `:androidApp:testDebugUnitTest`; rerun the focused command above before distributing an APK.

Release builds use minification and resource shrinking:

```bash
./gradlew :androidApp:assembleRelease --no-daemon --max-workers=1
sha256sum androidApp/build/outputs/apk/release/androidApp-release.apk
```

The repository does not define a release signing configuration in `mobile/androidApp/build.gradle.kts`. Treat an unsigned or locally signed release as a build artifact only, never as a distributable pilot APK. Keep signing keys outside the repository.

## 2. API target

The default Android API target is `https://api.skatelab.ru/v1/`. For a non-production environment, set the target for the build without putting credentials in source:

```bash
API_BASE_URL=https://api.example.invalid/v1/ \
  ./gradlew :androidApp:assembleDebug --no-daemon --max-workers=1
```

For the production read-only health check, use a machine with network access:

```bash
curl --fail --silent --show-error https://api.skatelab.ru/v1/health
```

Expected response is SkateLab JSON, for example `{"status":"ok"}`. Do not paste tokens, response headers containing credentials, or personal session data into release notes.

## 3. Synthetic BLE and report smoke

Until WT901 hardware is available, use the deterministic mocked/replay path already covered by the mobile capture tests and the synthetic fixtures from Tasks 1 and 3. The report must make the following states visible:

1. No IMU artifacts: `Sensor fusion: unavailable`.
2. Paired fixture artifacts: `Sensor fusion: synthetic/unvalidated`.
3. Paired result with diagnostics: values appear under `Measured diagnostics (not skating scores)`; `sensor_confidence` is never shown as skating quality.
4. Decode or processing failure: `Sensor fusion: unavailable` and the server error remains visible.
5. Axel result: at most one server recommendation is shown under `Axel recommendation`.

Do not turn a failed stream into an empty successful result, and do not infer sensor accuracy from a green heuristic range.

## 4. Install and manual smoke

After a successful debug build, install only on an approved test device/emulator using the existing containerized E2E setup under `mobile/e2e/`.

- Log in with a test account; never use a production password in a script.
- Run the existing capture/replay flow with both logical sensor sides.
- Confirm upload persists the session and processing reaches the result screen.
- Open the session detail and verify the provenance state, diagnostics wording, and Axel recommendation.
- Trigger/replay a missing or corrupt stream and verify the visible failed state.
- Capture the APK checksum, build variant, API target, fixture ID, device/emulator image, and date in the release record.

Host ADB should not be used when the containerized emulator is active. A physical hardware smoke is a separate gate and remains pending.

## 5. Hardware handoff

When WT901 sensors arrive, repeat the same flow with labelled real attempts:

- Confirm both streams contain samples and monotonic timestamps.
- Measure offset and rate errors against the plan thresholds.
- Collect 10-20 Axel attempts from 3-5 skaters.
- Have a coach label take-off/landing and compare one metric.
- Keep the report marked unvalidated until that evidence is reviewed.

Only after this gate should thresholds, workflow, or supported elements be changed.
