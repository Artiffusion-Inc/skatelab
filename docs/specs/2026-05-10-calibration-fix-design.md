# Calibration Fix Design

## Problem

Four bugs in the calibration pipeline:

### P0: Gyro threshold uses wrong units

`CalibrateSensorUseCase.kt:74-80` — `gyroX/Y/Z` are already in deg/s (WT901 SCALE_GYRO = 2000/32768), but the code divides by `DEG_TO_RAD` (~0.0175), turning a 10°/s threshold into ~571°/s. Every sample passes as "still" — the filter is non-functional.

### P0: No warm-up zero filtering

`CalibrateSensorUseCase` doesn't filter WT901 warm-up zeros (first ~0.5-1s after start streaming, acc ≈ 0). `ImuCollector` already has this filter. These zero samples pass the stillness check and corrupt the mean quaternion.

### P1: Sequential calibration breaks frame consistency

`CalibrateSensorUseCase.invoke(sensorId)` calibrates one sensor at a time. LEFT and RIGHT sensors are calibrated at different moments, so `quatRef` values refer to different poses. For correct `quatRef⁻¹ * q_sample` correction, both sensors must be calibrated simultaneously from the same pose.

### P1: CalibrationViewModel calls calibrate per-sensor

`CalibrationViewModel.calibrate(sensorId)` triggers one sensor's calibration. The UI has separate buttons per sensor. Should be a single "Calibrate Both" action.

## Solution (Approach A)

### 1. Fix gyro threshold

`gyroX/Y/Z` are in deg/s. Remove the `DEG_TO_RAD` conversion:

```kotlin
// BEFORE (BROKEN):
val gyroRad = sqrt((sample.gyroX * sample.gyroX + ...).toDouble())
val gyroDeg = gyroRad / DEG_TO_RAD  // gyroRad is ALREADY in deg/s!
if (gyroDeg <= ANGULAR_VELOCITY_THRESHOLD_DEG_S) { ... }

// AFTER (FIXED):
val gyroMagDegS = sqrt((sample.gyroX * sample.gyroX + sample.gyroY * sample.gyroY + sample.gyroZ * sample.gyroZ).toDouble())
if (gyroMagDegS <= ANGULAR_VELOCITY_THRESHOLD_DEG_S) { ... }
```

Remove the now-unused `DEG_TO_RAD` constant.

### 2. Add warm-up zero filter to CalibrateSensorUseCase

Reuse the same threshold as `ImuCollector` (acc magnitude >= 1.0 m/s²):

```kotlin
companion object {
    private const val WARMUP_MIN_ACC_MAGNITUDE = 1.0f
    // ...
}

// In collectStillSamples:
if (accMag < WARMUP_MIN_ACC_MAGNITUDE) return@collect  // discard warm-up zeros
```

### 3. Parallel calibration of both sensors

Replace single-sensor `invoke(sensorId)` with `invokeBoth()` that:

1. Starts streaming on BOTH sensors via `bleRepository.startStreaming(LEFT)` and `startStreaming(RIGHT)` in parallel (`async`/`awaitAll`)
2. Collects still samples for both sensors simultaneously from the shared `imuSamples` flow
3. Stops streaming on both sensors
4. Computes mean quaternion for each sensor independently
5. Returns `Map<SensorId, CalibrationData>`

```kotlin
suspend fun invokeBoth(): Result<Map<SensorId, CalibrationData>>
```

### 4. Update CalibrationViewModel and CalibrationScreen

- `CalibrationViewModel.calibrateBoth()` calls `invokeBoth()`, updates both `_leftCalibration` and `_rightCalibration`, sets `SessionState.calibration`
- Remove `calibrate(sensorId)` method (or deprecate)
- `CalibrationScreen`: single "Откалибровать оба" button instead of per-sensor buttons
- Keep live quaternion preview per sensor (already works)

### 5. Keep CalibrateSensorUseCase.invoke(sensorId) as internal fallback

The single-sensor method stays available for testing and edge cases, but `invokeBoth()` is the primary entry point.

## Interface Changes

- `CalibrateSensorUseCase`: add `suspend fun invokeBoth(): Result<Map<SensorId, CalibrationData>>`
- `CalibrationViewModel`: add `fun calibrateBoth()`, deprecate `fun calibrate(sensorId)`
- `CalibrationScreen`: single button "Калибровка" that calls `calibrateBoth()`
- No changes to `CalibrationData`, `CaptureSession`, or export format

## What stays unchanged

- `computeMeanQuaternion()` algorithm (running mean with hemisphere consistency)
- `Wt901Parser` quaternion parsing
- `ImuCollector` warm-up filter (already correct)
- `ManifestBuilder` calibration export format
- `SessionRepositoryImpl` session save/load