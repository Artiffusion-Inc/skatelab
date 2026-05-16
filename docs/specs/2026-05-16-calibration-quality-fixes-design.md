# Calibration Quality Fixes Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 quality bugs in CalibrateSensorUseCase: wrong hemisphere flip, suboptimal mean quaternion, eigendecomposition math error, too-permissive still-detection thresholds, early termination + missing minimum sample count.

**Architecture:** Replace arithmetic mean quaternion with Markley eigendecomposition. Use first sample as hemisphere reference. Tighten still-detection thresholds. Remove MAX_STILL_SAMPLES limit. Add MIN_STILL_SAMPLES safeguard.

**Tech Stack:** Kotlin, Android, JUnit 4 + MockK

---

## Background

Device testing of the calibration flow revealed:

1. **Hemisphere flip uses running mean as reference** — running mean is unnormalized, drifts over 500+ samples, causing spurious flips that corrupt the result.
2. **Arithmetic mean quaternion** — simple averaging + normalization is a poor approximation. The correct method is eigendecomposition of the outer-product matrix M = Σ(q_i ⊗ q_i^T) (Markley 2008).
3. **Eigendecomposition off-diagonal halving error** — the spec originally accumulated only upper-triangle elements then divided off-diagonals by 2, claiming "M[i][j] = M[j][i]". But each off-diagonal was only accumulated once, so halving makes them half the true value. **Remove all `mXY /= 2f` lines.** (Confirmed by Markley Eq. 12: M = Σ q_i q_i^T, no factor of 1/2.)
4. **GYRO_THRESHOLD = 10°/s too permissive** — allows samples with real rotational motion. WT901 noise floor ~0.5°/s, resolution ~0.061°/s/LSB. 10°/s is slow head turn.
5. **MAX_STILL_SAMPLES = 500 terminates early** — at 100Hz, 500 samples ≈ 5s. No minimum sample count — calibration could succeed on 1 sample.

## Bug 1: Hemisphere flip uses running mean as reference

**File:** `CalibrateSensorUseCase.kt`, `computeMeanQuaternion()`

**Current (broken):**
```kotlin
var refW = samples.first().quatW
var refX = samples.first().quatX
var refY = samples.first().quatY
var refZ = samples.first().quatZ

for (sample in samples) {
    var qW = sample.quatW; ...
    val dot = qW * refW + qX * refX + qY * refY + qZ * refZ
    if (dot < 0f) { qW = -qW; ... }
    sumW += qW; ...
    refW = sumW / count  // running mean — unnormalized!
    refX = sumX / count; ...
}
```

The running mean `refW = sumW / count` is never normalized. As samples accumulate, the unnormalized mean drifts. If it passes through zero, the dot product flips sign for all subsequent samples, corrupting the result.

**Fix:** Use the first sample as a fixed reference for hemisphere consistency. The first sample is guaranteed to be in the correct hemisphere. No running mean needed.

> **Note:** For the Markley method, hemisphere flip is mathematically redundant because M = Σ(q_i q_i^T) is sign-invariant (−q)(−q)^T = qq^T (Markley, p. 3). We keep the flip for defensive coding and clarity.

```kotlin
val refW = samples.first().quatW
val refX = samples.first().quatX
val refY = samples.first().quatY
val refZ = samples.first().quatZ
```

## Bug 2: Arithmetic mean quaternion → eigendecomposition

**File:** `CalibrateSensorUseCase.kt`, `computeMeanQuaternion()`

**Current:** Sum quaternions, normalize. This minimizes L2 distance in quaternion space, which is NOT the same as minimizing angular distance. For noisy IMU data with ~0.5° jitter the accumulated error is significant.

**Fix:** Markley (2008) method — compute the 4×4 outer-product matrix M = Σ(q_i q_i^T), then the mean quaternion is the eigenvector corresponding to the largest eigenvalue. This is the maximum-likelihood estimate of the mean rotation.

```kotlin
private fun computeMeanQuaternion(samples: List<ImuSample>): FloatArray {
    val refW = samples.first().quatW
    val refX = samples.first().quatX
    val refY = samples.first().quatY
    val refZ = samples.first().quatZ

    // Accumulate outer product M = Σ(q_i q_i^T) with hemisphere flip
    var m00 = 0f; var m01 = 0f; var m02 = 0f; var m03 = 0f
    var m11 = 0f; var m12 = 0f; var m13 = 0f
    var m22 = 0f; var m23 = 0f
    var m33 = 0f

    for (sample in samples) {
        var qW = sample.quatW
        var qX = sample.quatX
        var qY = sample.quatY
        var qZ = sample.quatZ

        // Hemisphere consistency: flip if dot(q_i, q_ref) < 0
        if (qW * refW + qX * refX + qY * refY + qZ * refZ < 0f) {
            qW = -qW; qX = -qX; qY = -qY; qZ = -qZ
        }

        m00 += qW * qW; m01 += qW * qX; m02 += qW * qY; m03 += qW * qZ
        m11 += qX * qX; m12 += qX * qY; m13 += qX * qZ
        m22 += qY * qY; m23 += qY * qZ
        m33 += qZ * qZ
    }

    // M is symmetric: m10=m01, m20=m02, m21=m12, m30=m03, m31=m13, m32=m23
    // DO NOT halve off-diagonals — each was accumulated once per sample
    val m10 = m01; val m20 = m02; val m21 = m12; val m30 = m03; val m31 = m13; val m32 = m23

    return dominantEigenvector4x4(m00, m01, m02, m03, m10, m11, m12, m13, m20, m21, m22, m23, m30, m31, m32, m33)
}
```

**Key correction:** The original spec had `m01 /= 2f; m02 /= 2f; ...` which is **mathematically wrong**. Each off-diagonal `m01 += qW * qX` accumulates exactly once per sample — the same as M[j][i] = M[i][j] by construction. Halving them gives half the true matrix value, corrupting the eigenvector. The fix uses explicit symmetric aliases (`m10 = m01`, etc.) to make the full matrix visible to the eigenvector solver without any halving.

**Eigendecomposition:** Power iteration for the dominant eigenvector of a 4×4 symmetric PSD matrix. 20 iterations guarantees convergence even under adverse eigenvalue ratios (cost < 1 µs on modern Android CPU). Initialize with the first sample quaternion rather than [1,0,0,0] to avoid pathological alignment with a near-orthogonal dominant eigenvector.

```kotlin
private fun dominantEigenvector4x4(
    m00: Float, m01: Float, m02: Float, m03: Float,
    m10: Float, m11: Float, m12: Float, m13: Float,
    m20: Float, m21: Float, m22: Float, m23: Float,
    m30: Float, m31: Float, m32: Float, m33: Float,
): FloatArray {
    // Power iteration for dominant eigenvector of symmetric 4×4 matrix
    // Initialize with data-aligned vector (not [1,0,0,0]) to avoid pathological cases
    var w = initW; var x = initX; var y = initY; var z = initZ
    for (i in 0 until 20) {
        val nw = m00 * w + m01 * x + m02 * y + m03 * z
        val nx = m10 * w + m11 * x + m12 * y + m13 * z
        val ny = m20 * w + m21 * x + m22 * y + m23 * z
        val nz = m30 * w + m31 * x + m32 * y + m33 * z
        val norm = sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
        w = nw / norm; x = nx / norm; y = ny / norm; z = nz / norm
    }
    return floatArrayOf(w, x, y, z)
}
```

The init vector is passed from `computeMeanQuaternion` as the first sample quaternion (already hemisphere-normalized).

## Bug 3: Still-detection thresholds too permissive

**File:** `CalibrateSensorUseCase.kt`, `collectStillSamplesBoth()`

**Current:**
- `ANGULAR_VELOCITY_THRESHOLD_DEG_S = 10.0` — allows slow rotational motion
- No acceleration magnitude check — samples with wrong orientation pass through

**Fix:**
- `ANGULAR_VELOCITY_THRESHOLD_DEG_S = 5.0` — ~5× the zero-drift spec (±1.0°/s), ~70× the RMS noise. Rejects real motion, accepts hand tremor (1-3°/s).
- Add `ACC_MAG_MIN = 9.3` and `ACC_MAG_MAX = 10.3` — tight ±0.5 m/s² window around gravity (9.81 m/s²), vs. WT901 acc noise+drift of ±0.4 m/s². The previous 9.0-11.0 range was ~25× wider than the sensor's noise+drift envelope.

> **Unit verification:** `ImuSample.gyroX/Y/Z` are in °/s (parser: `SCALE_GYRO = 2000f / 32768f`). `ImuSample.accX/Y/Z` are in m/s² (parser: `SCALE_ACC = 16f * 9.80665f / 32768f`). Thresholds are in matching units — no conversion needed.

```kotlin
private const val ANGULAR_VELOCITY_THRESHOLD_DEG_S = 5.0
private const val ACC_MAG_MIN = 9.3
private const val ACC_MAG_MAX = 10.3

// In collectStillSamplesBoth:
val accMag = sqrt(sample.accX * sample.accX + sample.accY * sample.accY + sample.accZ * sample.accZ)
val gyroMagDegS = sqrt(sample.gyroX * sample.gyroX + sample.gyroY * sample.gyroY + sample.gyroZ * sample.gyroZ)
val isStill = gyroMagDegS <= ANGULAR_VELOCITY_THRESHOLD_DEG_S &&
              accMag >= ACC_MAG_MIN && accMag <= ACC_MAG_MAX
```

## Bug 4: Early termination removes useful data; no minimum sample count

**File:** `CalibrateSensorUseCase.kt`, `collectStillSamplesBoth()`

**Current:**
```kotlin
if (leftSamples.size >= MAX_STILL_SAMPLES && rightSamples.size >= MAX_STILL_SAMPLES) break
```

This terminates at ~5s when both sensors reach 500 still samples. More samples = better eigendecomposition. Also, there is no minimum sample count — calibration could succeed on as few as 1 sample, producing a statistically meaningless result.

**Fix:** Remove `MAX_STILL_SAMPLES` limit entirely. Let the 10s timer run to completion. Add `MIN_STILL_SAMPLES = 50` (5s at 10Hz) as a minimum. Return a specific failure if either sensor doesn't accumulate enough still samples.

```kotlin
private const val MIN_STILL_SAMPLES = 50

// After collection loop:
if (leftSamples.size < MIN_STILL_SAMPLES || rightSamples.size < MIN_STILL_SAMPLES) {
    return Result.failure(IllegalStateException(
        "Insufficient still samples: left=${leftSamples.size}, right=${rightSamples.size}. " +
        "Hold sensors still for at least 5 seconds."
    ))
}
```

Remove the `MAX_STILL_SAMPLES` constant and the early-break condition entirely.

## Files to Change

| File | Change |
|------|--------|
| `CalibrateSensorUseCase.kt` | Replace `computeMeanQuaternion` with eigendecomposition (no off-diagonal halving); fix hemisphere flip; use first sample as power iteration init; 20 iterations; tighten still-detection (5°/s, 9.3-10.3 m/s²); remove MAX_STILL_SAMPLES; add MIN_STILL_SAMPLES=50 |
| `CalibrateSensorUseCaseTest.kt` | Add tests for eigenvector correctness, hemisphere flip, still-detection thresholds, MIN_STILL_SAMPLES boundary, off-diagonal values |

All paths relative to `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/` for source, `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/` for tests.

## Testing

- Unit test: `computeMeanQuaternion` with known quaternion set → correct mean (within 0.1° angular distance)
- Unit test: Hemisphere flip — samples with alternating signs → all normalized to same hemisphere
- Unit test: Still-detection — gyro ≤ 5°/s accepted, gyro > 5°/s rejected; acc 9.3-10.3 accepted, outside rejected
- Unit test: `dominantEigenvector4x4` — known symmetric matrix → correct eigenvector (compare to numpy reference)
- Unit test: Off-diagonal matrix elements — verify `m01 == qW*qX` summed, NOT halved
- Unit test: MIN_STILL_SAMPLES — < 50 samples returns failure with descriptive message
- Integration: calibrate on device, verify quatRef values are stable across repeated calibrations

## References

- Markley, F. L. (2008). "Averaging Quaternions." *Journal of Guidance, Control, and Dynamics*, 30(4), 1193-1197. Eq. (12)-(13).
- WT901BLECL datasheet: gyro zero drift ±0.5-1.0°/s, acc zero drift ±20-40 mg, resolution 0.061°/s/LSB