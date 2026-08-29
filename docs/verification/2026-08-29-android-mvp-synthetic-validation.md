# Android MVP synthetic validation

Status: pilot software checks only. Hardware validation is pending; no claim in this document establishes sensor accuracy, skating quality, or coach validity.

## Scope

Task 4 report/release checks cover the existing session contracts and the two report surfaces:

- Frontend session detail presents sensor provenance, explicit `synthetic/unvalidated` status, measured sensor diagnostics, unavailable data, and a single Axel recommendation.
- Android session detail presents the same provenance boundary from the fields currently available to the shared client. Sensor metrics are kept out of the skating metric cards and are labelled as diagnostics, not scores.
- A failed analysis remains visible as an error and is not presented as a valid fused result.

The current Android `SessionResponse` does not expose the three artifact keys. Android therefore identifies a completed multimodal result from the sensor-fusion diagnostic metric set already delivered in the session result. A future explicit provenance field should replace this inference when the API contract is expanded.

## Fixture and contract inventory

The plan names these fixture cases: `valid-pair`, `gap`, `drift`, and `corrupt`. No fixture files were present under `ml/tests/sensor_fusion/fixtures/` when this Task 4 lane was checked, so this document does not claim those binary cases were executed here. Their decoder/E2E evidence belongs to Tasks 1 and 3.

For an independent review, exercise the report with these payload shapes:

| Case | Required report state | Evidence to check |
| --- | --- | --- |
| Absent IMU | `Sensor fusion: unavailable` | No IMU keys and no sensor diagnostics. |
| Synthetic paired result | `Sensor fusion: synthetic/unvalidated` | `imu_left_key`, `imu_right_key`, and `manifest_key` are present; report shows the validation warning. |
| Valid multimodal result | Measured diagnostics | Sensor metrics such as `sensor_confidence`, `imu_peak_delta`, `imu_offset_error`, and `imu_rate_error` are shown under `Measured diagnostics (not skating scores)`. |
| Corrupt stream failure | `Sensor fusion: unavailable` plus analysis error | Session status is `failed`; `error_message` remains visible and no valid fused status is shown. |

## Commands run

Commands run in this checkout:

```bash
cd frontend && bun run typecheck
# passed: fumadocs generation and TypeScript no-emit check

cd frontend && bun run lint
# passed after formatting the assigned session page

cd mobile && ./gradlew ktlintCheck :shared:allTests :androidApp:testDebugUnitTest :androidApp:assembleDebug --no-daemon --max-workers=1
# first run: ktlint found one assigned-file formatting violation; fixed before rerun
# rerun: Kotlin compilation and ktlint passed, but the Gradle daemon disappeared during testDebugUnitTest
```

The frontend checks are green. The Android command is not a green release gate until the unit-test daemon failure is reproduced or the environment is stabilized. No release APK checksum is claimed by this document.

## Known limits

- `synthetic/unvalidated` is deliberately a provenance warning for the current pilot; it is not a confidence score and must not be read as skating quality.
- Sensor diagnostics are values emitted by the existing fusion pipeline. Their thresholds and heuristic meaning are not hardware-validated.
- The Android report cannot distinguish synthetic from real hardware without an explicit API provenance field, so paired diagnostics are treated as unvalidated pilot data.
- Release signing, device install, production API smoke, mocked BLE replay, and real WT901 sessions remain pending.
- No UI test was added in this lane because the task ownership contract limits edits to the two report files and `docs/verification`/`docs/runbooks`. Existing frontend type/lint and Android compile/ktlint checks are the available focused evidence.

Hardware gate: pending collection of labelled real WT901 sessions, per the MVP plan.
