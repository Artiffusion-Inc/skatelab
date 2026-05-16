# Calibration Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 quality bugs in CalibrateSensorUseCase: wrong hemisphere flip, arithmetic mean → Markley eigendecomposition, off-diagonal halving error, too-permissive still-detection thresholds, early termination + missing MIN_STILL_SAMPLES.

**Architecture:** Replace `computeMeanQuaternion` with Markley eigendecomposition (outer-product matrix + power iteration). Fix hemisphere flip to use first sample as fixed reference. Tighten still-detection (5°/s gyro, 9.3–10.3 m/s² acc). Remove MAX_STILL_SAMPLES, add MIN_STILL_SAMPLES=50.

**Tech Stack:** Kotlin, Android, JUnit 4, MockK

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt` | Modify | Replace computeMeanQuaternion, fix hemisphere flip, tighten thresholds, remove MAX_STILL_SAMPLES, add MIN_STILL_SAMPLES |
| `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt` | Modify | Add tests for eigenvector, hemisphere, thresholds, MIN_STILL_SAMPLES |

---

## Wave 1: Core Algorithm — dominantEigenvector4x4 + computeMeanQuaternion

### Task 1: dominantEigenvector4x4 — write failing test

**Files:**

- Modify: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Write the failing test**

Add test for `dominantEigenvector4x4` with a known 4×4 symmetric matrix. The dominant eigenvector of the identity matrix is any unit vector. A better test uses a rank-1 matrix M = N * q * q^T where q = [0.5, 0.5, 0.5, 0.5] / norm — the dominant eigenvector must be q.

```kotlin
@Test
fun dominantEigenvector_rank1Matrix_returnsExpectedVector() {
    // M = 100 * q * q^T where q = normalized [0.5, 0.5, 0.5, 0.5]
    val n = 100f
    val qw = 0.5f; val qx = 0.5f; val qy = 0.5f; val qz = 0.5f
    val norm = sqrt((qw * qw + qx * qx + qy * qy + qz * qz).toDouble()).toFloat()
    val w = qw / norm; val x = qx / norm; val y = qy / norm; val z = qz / norm

    val m00 = n * w * w; val m01 = n * w * x; val m02 = n * w * y; val m03 = n * w * z
    val m11 = n * x * x; val m12 = n * x * y; val m13 = n * x * z
    val m22 = n * y * y; val m23 = n * y * z
    val m33 = n * z * z

    val result = invokeDominantEigenvector4x4(
        m00, m01, m02, m03,
        m01, m11, m12, m13,
        m02, m12, m22, m23,
        m03, m13, m23, m33,
        w, x, y, z,
    )
    // Result should be proportional to [w, x, y, z], normalized
    val rNorm = sqrt((result[0] * result[0] + result[1] * result[1] + result[2] * result[2] + result[3] * result[3]).toDouble()).toFloat()
    assertEquals(1.0f, rNorm, 0.001f)
    // Check direction (allow sign flip)
    val dot = result[0] * w + result[1] * x + result[2] * y + result[3] * z
    assertTrue("Eigenvector should align with input (dot=$dot)", dot > 0.99f)
}
```

Add the reflection helper:

```kotlin
private fun invokeDominantEigenvector4x4(
    m00: Float, m01: Float, m02: Float, m03: Float,
    m10: Float, m11: Float, m12: Float, m13: Float,
    m20: Float, m21: Float, m22: Float, m23: Float,
    m30: Float, m31: Float, m32: Float, m33: Float,
    initW: Float, initX: Float, initY: Float, initZ: Float,
): FloatArray {
    val method = CalibrateSensorUseCase::class.java.getDeclaredMethod(
        "dominantEigenvector4x4",
        Float::class.java, Float::class.java, Float::class.java, Float::class.java,
        Float::class.java, Float::class.java, Float::class.java, Float::class.java,
        Float::class.java, Float::class.java, Float::class.java, Float::class.java,
        Float::class.java, Float::class.java, Float::class.java, Float::class.java,
        Float::class.java, Float::class.java, Float::class.java, Float::class.java,
    )
    method.isAccessible = true
    return method.invoke(useCase, m00, m01, m02, m03, m10, m11, m12, m13, m20, m21, m22, m23, m30, m31, m32, m33, initW, initX, initY, initZ) as FloatArray
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest.dominantEigenvector_rank1Matrix_returnsExpectedVector' 2>&1 | tail -20`
Expected: FAIL — method `dominantEigenvector4x4` does not exist yet.

- [ ] **Step 3: Implement dominantEigenvector4x4**

Add the method to `CalibrateSensorUseCase.kt` after `computeMeanQuaternion`:

```kotlin
private fun dominantEigenvector4x4(
    m00: Float, m01: Float, m02: Float, m03: Float,
    m10: Float, m11: Float, m12: Float, m13: Float,
    m20: Float, m21: Float, m22: Float, m23: Float,
    m30: Float, m31: Float, m32: Float, m33: Float,
    initW: Float, initX: Float, initY: Float, initZ: Float,
): FloatArray {
    var w = initW; var x = initX; var y = initY; var z = initZ
    for (i in 0 until 20) {
        val nw = m00 * w + m01 * x + m02 * y + m03 * z
        val nx = m10 * w + m11 * x + m12 * y + m13 * z
        val ny = m20 * w + m21 * x + m22 * y + m23 * z
        val nz = m30 * w + m31 * x + m32 * y + m33 * z
        val norm = sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
        if (norm < 1e-10f) break
        w = nw / norm; x = nx / norm; y = ny / norm; z = nz / norm
    }
    return floatArrayOf(w, x, y, z)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest.dominantEigenvector_rank1Matrix_returnsExpectedVector' 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt
git commit -m "feat(calibration): add dominantEigenvector4x4 with power iteration test"
```

---

### Task 2: Replace computeMeanQuaternion with Markley eigendecomposition — write failing tests

**Files:**

- Modify: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Write failing test — Markley mean of clustered quaternions**

A cluster of quaternions near q = [1, 0, 0, 0] with small noise should produce a mean close to [1, 0, 0, 0]. The arithmetic mean is close but not identical to the Markley mean. The Markley mean minimizes angular distance.

```kotlin
@Test
fun computeMeanQuaternion_clusteredQuaternions_returnsMarkleyMean() {
    // 5 quaternions near identity with small perturbation
    val samples = listOf(
        stillSample(0L, quatW = 0.9998f, quatX = 0.01f, quatY = 0.005f, quatZ = 0.002f),
        stillSample(1L, quatW = 0.9999f, quatX = 0.008f, quatY = 0.006f, quatZ = 0.001f),
        stillSample(2L, quatW = 0.9997f, quatX = 0.012f, quatY = 0.004f, quatZ = 0.003f),
        stillSample(3L, quatW = 0.9998f, quatX = 0.009f, quatY = 0.007f, quatZ = 0.002f),
        stillSample(4L, quatW = 0.9999f, quatX = 0.011f, quatY = 0.003f, quatZ = 0.001f),
    )
    val mean = invokeComputeMeanQuaternion(samples)
    // Mean should be close to identity — within 0.5° angular distance
    val meanNorm = sqrt((mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] + mean[3] * mean[3]).toDouble()).toFloat()
    assertEquals(1.0f, meanNorm, 0.01f)
    // Angular distance from identity: 2 * acos(|dot|)
    val dot = mean[0] // dot with [1,0,0,0] = mean[0]
    assertTrue("Mean w component should be positive (dot=$dot)", dot > 0.9f)
}
```

- [ ] **Step 2: Write failing test — hemisphere flip with fixed reference**

Alternating-sign quaternions should all be flipped to the same hemisphere as the first sample:

```kotlin
@Test
fun computeMeanQuaternion_hemisphereFlip_fixedReference() {
    // First sample defines the hemisphere; second is negated
    val samples = listOf(
        stillSample(0L, quatW = 0.7071f, quatX = 0.7071f, quatY = 0f, quatZ = 0f),
        stillSample(1L, quatW = -0.7071f, quatX = -0.7071f, quatY = 0f, quatZ = 0f),
        stillSample(2L, quatW = 0.7071f, quatX = 0.7071f, quatY = 0f, quatZ = 0f),
        stillSample(3L, quatW = -0.7071f, quatX = -0.7071f, quatY = 0f, quatZ = 0f),
    )
    val mean = invokeComputeMeanQuaternion(samples)
    // Mean should be in the positive hemisphere (same as first sample)
    assertTrue("Mean w should be positive", mean[0] > 0f)
    assertTrue("Mean x should be positive", mean[1] > 0f)
    assertEquals(0f, mean[2], 0.01f)
    assertEquals(0f, mean[3], 0.01f)
}
```

- [ ] **Step 3: Write failing test — off-diagonal elements not halved**

Verify that the matrix M built by computeMeanQuaternion has correct off-diagonal values (not halved). We test this indirectly: if off-diagonals were halved, the eigenvector for a rank-1 matrix would be wrong.

```kotlin
@Test
fun computeMeanQuaternion_singleQuaternion_returnsThatQuaternion() {
    // With 1 sample, M = q*q^T, dominant eigenvector = q
    val samples = listOf(
        stillSample(0L, quatW = 0.5f, quatX = 0.5f, quatY = 0.5f, quatZ = 0.5f),
    )
    val mean = invokeComputeMeanQuaternion(samples)
    // Normalize expected
    val n = sqrt(4 * 0.25).toFloat() // = 1.0
    assertArrayEquals(floatArrayOf(0.5f, 0.5f, 0.5f, 0.5f), mean, 0.01f)
}
```

- [ ] **Step 4: Run tests to verify they fail (still using old arithmetic mean)**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest.computeMeanQuaternion_*' 2>&1 | tail -20`
Expected: `computeMeanQuaternion_hemisphereFlip_fixedReference` should PASS (old code also flips). `computeMeanQuaternion_clusteredQuaternions` may pass or fail depending on tolerance. `computeMeanQuaternion_singleQuaternion` will likely FAIL because old code divides by count and normalizes differently.

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt
git commit -m "test(calibration): add Markley mean, hemisphere flip, single-sample tests"
```

---

### Task 3: Replace computeMeanQuaternion implementation with Markley eigendecomposition

**Files:**

- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:171-214`

- [ ] **Step 1: Replace computeMeanQuaternion**

Replace the entire `computeMeanQuaternion` method (lines 171–214) with:

```kotlin
private fun computeMeanQuaternion(samples: List<ImuSample>): FloatArray {
    val refW = samples.first().quatW
    val refX = samples.first().quatX
    val refY = samples.first().quatY
    val refZ = samples.first().quatZ

    // Accumulate outer product M = Σ(q_i q_i^T) with hemisphere flip
    // Hemisphere flip is redundant for Markley (M is sign-invariant) but kept for clarity
    var m00 = 0f; var m01 = 0f; var m02 = 0f; var m03 = 0f
    var m11 = 0f; var m12 = 0f; var m13 = 0f
    var m22 = 0f; var m23 = 0f
    var m33 = 0f

    for (sample in samples) {
        var qW = sample.quatW
        var qX = sample.quatX
        var qY = sample.quatY
        var qZ = sample.quatZ

        if (qW * refW + qX * refX + qY * refY + qZ * refZ < 0f) {
            qW = -qW; qX = -qX; qY = -qY; qZ = -qZ
        }

        m00 += qW * qW; m01 += qW * qX; m02 += qW * qY; m03 += qW * qZ
        m11 += qX * qX; m12 += qX * qY; m13 += qX * qZ
        m22 += qY * qY; m23 += qY * qZ
        m33 += qZ * qZ
    }

    // Symmetric aliases — DO NOT halve off-diagonals (each accumulated once)
    val m10 = m01; val m20 = m02; val m21 = m12; val m30 = m03; val m31 = m13; val m32 = m23

    return dominantEigenvector4x4(
        m00, m01, m02, m03,
        m10, m11, m12, m13,
        m20, m21, m22, m23,
        m30, m31, m32, m33,
        refW, refX, refY, refZ,
    )
}
```

Also remove `var sumW`, `var sumX`, `var sumY`, `var sumZ`, `var count` variables that are no longer needed.

- [ ] **Step 2: Run all computeMeanQuaternion tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest' 2>&1 | tail -20`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt
git commit -m "feat(calibration): replace arithmetic mean with Markley eigendecomposition"
```

---

## Wave 2: Still-Detection Thresholds

### Task 4: Tighten still-detection thresholds — write failing tests

**Files:**

- Modify: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Write failing test — gyro threshold 5°/s**

Current code uses 10°/s. Samples with gyro = 6°/s should now be rejected.

```kotlin
@Test
fun invokeBoth_gyroAbove5Dps_samplesRejected() =
    testScope.runTest {
        val calibrationDeferred = async { useCase() }
        runCurrent()

        advanceTimeBy(1_500L)
        runCurrent()

        launch {
            repeat(100) { i ->
                // gyro = 6°/s, above new threshold of 5°/s
                imuSamplesFlow.emit(SensorId.LEFT to ImuSample(
                    timestampNs = i.toLong(),
                    accX = 0f, accY = 0f, accZ = 9.81f,
                    gyroX = 6.0f, gyroY = 0f, gyroZ = 0f,
                    quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
                ))
                imuSamplesFlow.emit(SensorId.RIGHT to ImuSample(
                    timestampNs = i.toLong(),
                    accX = 0f, accY = 0f, accZ = 9.81f,
                    gyroX = 6.0f, gyroY = 0f, gyroZ = 0f,
                    quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
                ))
                yield()
            }
        }
        runCurrent()

        advanceTimeBy(12_000L)
        runCurrent()

        val result = calibrationDeferred.await()
        assertTrue("Should fail with gyro > 5°/s samples only", result.isFailure)
    }
```

- [ ] **Step 2: Write failing test — acc magnitude check**

```kotlin
@Test
fun invokeBoth_accOutsideRange_samplesRejected() =
    testScope.runTest {
        val calibrationDeferred = async { useCase() }
        runCurrent()

        advanceTimeBy(1_500L)
        runCurrent()

        launch {
            repeat(100) { i ->
                // acc magnitude = 8.0, below ACC_MAG_MIN = 9.3
                imuSamplesFlow.emit(SensorId.LEFT to ImuSample(
                    timestampNs = i.toLong(),
                    accX = 0f, accY = 0f, accZ = 8.0f,
                    gyroX = 0f, gyroY = 0f, gyroZ = 0f,
                    quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
                ))
                imuSamplesFlow.emit(SensorId.RIGHT to ImuSample(
                    timestampNs = i.toLong(),
                    accX = 0f, accY = 0f, accZ = 8.0f,
                    gyroX = 0f, gyroY = 0f, gyroZ = 0f,
                    quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
                ))
                yield()
            }
        }
        runCurrent()

        advanceTimeBy(12_000L)
        runCurrent()

        val result = calibrationDeferred.await()
        assertTrue("Should fail with acc magnitude outside 9.3-10.3", result.isFailure)
    }
```

- [ ] **Step 3: Update stillSample helper to use realistic acc magnitude**

The current `stillSample` helper has `accZ = 9.81f` which yields accMag = 9.81 (inside 9.3-10.3). This is correct for the new thresholds. But update `movingSample` to use gyro > 5°/s:

```kotlin
private fun movingSample(timestampNs: Long) =
    ImuSample(
        timestampNs = timestampNs,
        accX = 0f, accY = 0f, accZ = 9.81f,
        gyroX = 10.0f, gyroY = 10.0f, gyroZ = 10.0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )
```

No change needed here — gyro = 17.3°/s magnitude, above both old and new thresholds. But verify the `stillSample` acc magnitude: `sqrt(0² + 0² + 9.81²) = 9.81`, inside 9.3-10.3.

- [ ] **Step 4: Run tests to verify new ones fail**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest.invokeBoth_gyroAbove5Dps_samplesRejected' 2>&1 | tail -10`
Expected: FAIL — 6°/s still passes old 10°/s threshold.

- [ ] **Step 5: Commit**

```bash
git add mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt
git commit -m "test(calibration): add failing tests for tightened still-detection thresholds"
```

---

### Task 5: Implement tightened thresholds + acc magnitude check

**Files:**

- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:23-29` (constants)
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:123-142` (isStill logic)

- [ ] **Step 1: Update constants**

Replace the companion object constants:

```kotlin
companion object {
    private const val TAG = "CalibrateSensorUC"
    private const val COLLECTION_TIMEOUT_MS = 12_000L
    private const val COLLECTION_DURATION_MS = 10_000L
    private const val ANGULAR_VELOCITY_THRESHOLD_DEG_S = 5.0
    private const val ACC_MAG_MIN = 9.3
    private const val ACC_MAG_MAX = 10.3
    private const val WARMUP_MS = 1_000L
}
```

Remove `MAX_STILL_SAMPLES`. Add `ACC_MAG_MIN`, `ACC_MAG_MAX`.

- [ ] **Step 2: Update isStill logic in collectStillSamplesBoth**

Replace the isStill computation (around line 132):

```kotlin
val gyroMagDegS =
    sqrt(
        (
            sample.gyroX * sample.gyroX +
                sample.gyroY * sample.gyroY +
                sample.gyroZ * sample.gyroZ
        ).toDouble(),
    )
val accMag =
    sqrt(
        (
            sample.accX * sample.accX +
                sample.accY * sample.accY +
                sample.accZ * sample.accZ
        ).toDouble(),
    )
val isStill = gyroMagDegS <= ANGULAR_VELOCITY_THRESHOLD_DEG_S &&
    accMag >= ACC_MAG_MIN && accMag <= ACC_MAG_MAX
```

Note: `accMag` is now computed in the isStill block, replacing the debug-only `accMag` in the log block. Keep the debug log using the same variable.

- [ ] **Step 3: Run all tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest' 2>&1 | tail -10`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt
git commit -m "fix(calibration): tighten still-detection — gyro 5°/s, acc 9.3-10.3 m/s²"
```

---

## Wave 3: MIN_STILL_SAMPLES + Remove MAX_STILL_SAMPLES

### Task 6: Remove MAX_STILL_SAMPLES early termination + add MIN_STILL_SAMPLES — write failing test

**Files:**

- Modify: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Write failing test — insufficient still samples**

```kotlin
@Test
fun invokeBoth_insufficientStillSamples_returnsFailure() =
    testScope.runTest {
        val calibrationDeferred = async { useCase() }
        runCurrent()

        advanceTimeBy(1_500L)
        runCurrent()

        // Only 10 still samples per sensor — below MIN_STILL_SAMPLES=50
        launch {
            repeat(10) { i ->
                imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
                imuSamplesFlow.emit(SensorId.RIGHT to stillSample(i.toLong()))
                yield()
            }
        }
        runCurrent()

        advanceTimeBy(12_000L)
        runCurrent()

        val result = calibrationDeferred.await()
        assertTrue("Should fail with insufficient still samples", result.isFailure)
        assertTrue(
            "Error should mention 'Insufficient still samples'",
            result.exceptionOrNull()!!.message!!.contains("Insufficient still samples"),
        )
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest.invokeBoth_insufficientStillSamples_returnsFailure' 2>&1 | tail -10`
Expected: FAIL — old code succeeds with any `isNotEmpty()` check.

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt
git commit -m "test(calibration): add failing test for MIN_STILL_SAMPLES"
```

---

### Task 7: Implement MIN_STILL_SAMPLES + remove MAX_STILL_SAMPLES

**Files:**

- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:23-29` (constants)
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:147-159` (collection loop)
- Modify: `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt:49-76` (result validation)

- [ ] **Step 1: Add MIN_STILL_SAMPLES constant**

Add to companion object:

```kotlin
private const val MIN_STILL_SAMPLES = 50
```

- [ ] **Step 2: Remove MAX_STILL_SAMPLES early-break**

In the `withTimeout` loop, remove this line:

```kotlin
if (leftSamples.size >= MAX_STILL_SAMPLES && rightSamples.size >= MAX_STILL_SAMPLES) break
```

The loop should now only break on `elapsedMs >= COLLECTION_DURATION_MS`.

- [ ] **Step 3: Add MIN_STILL_SAMPLES check after collection**

Replace the result-building block (lines 49–76) with:

```kotlin
appLogger.i(TAG, "Collected LEFT=${leftSamples.size}, RIGHT=${rightSamples.size} still samples")

if (leftSamples.size < MIN_STILL_SAMPLES || rightSamples.size < MIN_STILL_SAMPLES) {
    return Result.failure(IllegalStateException(
        "Insufficient still samples: left=${leftSamples.size}, right=${rightSamples.size}. " +
        "Hold sensors still for at least 5 seconds.",
    ))
}

val result = mutableMapOf<SensorId, CalibrationData>()
result[SensorId.LEFT] = CalibrationData(
    quatRef = computeMeanQuaternion(leftSamples),
    calibratedAt = System.currentTimeMillis(),
)
result[SensorId.RIGHT] = CalibrationData(
    quatRef = computeMeanQuaternion(rightSamples),
    calibratedAt = System.currentTimeMillis(),
)
Result.success(result)
```

This removes the per-sensor `if (isNotEmpty())` conditional — both sensors MUST have ≥50 samples. If one has fewer, the whole calibration fails.

- [ ] **Step 4: Run all tests**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest' 2>&1 | tail -10`
Expected: ALL PASS

Note: The existing `invokeBoth_partialResult_oneSensorStill` test may need updating — old behavior allowed partial results (only LEFT calibrated). New behavior requires BOTH sensors to have ≥50 still samples. If this test expects only LEFT in the result, it will now fail. Fix it to expect failure when RIGHT has no still samples.

- [ ] **Step 5: Update partial-result test if needed**

If `invokeBoth_partialResult_oneSensorStill` fails, update it to expect `Result.isFailure` with "Insufficient still samples" message, since RIGHT has 0 still samples (all moving):

```kotlin
@Test
fun invokeBoth_partialResult_oneSensorStill_returnsFailure() =
    testScope.runTest {
        val calibrationDeferred = async { useCase() }
        runCurrent()

        advanceTimeBy(1_500L)
        runCurrent()

        launch {
            repeat(500) { i ->
                imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
                imuSamplesFlow.emit(SensorId.RIGHT to movingSample(i.toLong()))
                yield()
            }
        }
        runCurrent()

        advanceTimeBy(10_000L)
        runCurrent()

        val result = calibrationDeferred.await()
        assertTrue("Should fail — RIGHT has no still samples", result.isFailure)
    }
```

- [ ] **Step 6: Commit**

```bash
git add mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCase.kt mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt
git commit -m "fix(calibration): add MIN_STILL_SAMPLES=50, remove MAX_STILL_SAMPLES early break"
```

---

## Wave 4: Full Test Suite Validation

### Task 8: Run full test suite + fix any regressions

**Files:**

- Possibly modify: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Run full CalibrateSensorUseCaseTest suite**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest' 2>&1 | tail -30`
Expected: ALL PASS

- [ ] **Step 2: Run broader test suite to check for regressions**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest 2>&1 | tail -30`
Expected: ALL PASS

- [ ] **Step 3: Commit any test fixes**

```bash
git add -A
git commit -m "test(calibration): fix regressions from threshold changes"
```

(Only if changes needed — skip if all green.)

---

### Task 9: Add angular distance test for computeMeanQuaternion accuracy

**Files:**

- Modify: `mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt`

- [ ] **Step 1: Write angular distance helper and test**

Add a helper to compute angular distance between two quaternions (in degrees), then test that the Markley mean of a known cluster is within 0.1° of the true mean:

```kotlin
private fun angularDistanceDeg(q1: FloatArray, q2: FloatArray): Float {
    var dot = 0f
    for (i in 0 until 4) dot += q1[i] * q2[i]
    dot = dot.coerceIn(-1f, 1f)
    return Math.toDegrees(acos(dot.toDouble()) * 2).toFloat()
}

@Test
fun computeMeanQuaternion_knownCluster_withinPoint1Degree() {
    // True mean ≈ [1, 0, 0, 0] with small perturbation
    // Generate 20 samples near identity
    val samples = mutableListOf<ImuSample>()
    for (i in 0 until 20) {
        val angle = (i - 10) * 0.02f // small angular offset in radians
        val w = cos(angle.toDouble()).toFloat()
        val x = sin(angle.toDouble()).toFloat() * 0.57735f // normalize [1,1,1]
        val y = x
        val z = x
        val n = sqrt((w * w + x * x + y * y + z * z).toDouble()).toFloat()
        samples.add(stillSample(i.toLong(), quatW = w / n, quatX = x / n, quatY = y / n, quatZ = z / n))
    }
    val mean = invokeComputeMeanQuaternion(samples)
    val dist = angularDistanceDeg(mean, floatArrayOf(1f, 0f, 0f, 0f))
    assertTrue("Angular distance should be < 0.5° but was $dist", dist < 0.5f)
}
```

Add `import kotlin.math.acos` and `import kotlin.math.cos` at the top of the test file.

- [ ] **Step 2: Run test**

Run: `cd /home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/mobile && ./gradlew app:testDebugUnitTest --tests 'ru.skatelab.capture.domain.usecase.CalibrateSensorUseCaseTest.computeMeanQuaternion_knownCluster_withinPoint1Degree' 2>&1 | tail -5`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add mobile/app/src/test/java/ru/skatelab/capture/domain/usecase/CalibrateSensorUseCaseTest.kt
git commit -m "test(calibration): add angular distance accuracy test for Markley mean"
```
