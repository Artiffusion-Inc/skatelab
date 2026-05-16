# Calibration Spec 5-Agent Deep Review Report

**Date:** 2026-05-16
**Spec reviewed:** `docs/specs/2026-05-16-calibration-quality-fixes-design.md`
**Agents:** Math Correctness, Still-Detection Thresholds, Parallel/Async Architecture, Testing Strategy, BLE Protocol + Quaternion Format

---

## Critical Findings (Must Fix Before Implementation)

### 1. Off-diagonal matrix halving is mathematically incorrect (Agents 1, 2)

**Severity:** CRITICAL — breaks the Markley method entirely.

Original spec accumulated upper-triangle elements only, then divided all off-diagonals by 2:
```kotlin
m01 /= 2f; m02 /= 2f; m03 /= 2f
m12 /= 2f; m13 /= 2f; m23 /= 2f
```

Each `m01 += qW * qX` is accumulated **once** per sample. By symmetry, `m01 == m10` — no halving needed. Halving gives 50% of the true value, producing an incorrect eigenvector.

**Source:** Markley Eq. (12): M = Σ(q_i q_i^T). Reference MATLAB: `A = q*q' + A` (full rank-1 update, no halving).

**Fix applied:** Removed all `/= 2f` lines. Use explicit symmetric aliases (`m10 = m01`, etc.) for the full matrix passed to power iteration.

### 2. Power iteration initialization with [1,0,0,0] is risky (Agent 1)

If the true dominant eigenvector is nearly orthogonal to [1,0,0,0], initial projection is extremely small. In float32, this can cause delayed convergence.

**Fix applied:** Initialize with the first sample quaternion (already hemisphere-normalized). Guarantees non-zero projection onto the data subspace.

### 3. No minimum sample count (Agent 2)

Original spec removed MAX_STILL_SAMPLES but added no MIN_STILL_SAMPLES. Calibration could succeed on 1 sample — statistically meaningless.

**Fix applied:** Added `MIN_STILL_SAMPLES = 50` (5s at 10Hz). Returns descriptive failure if insufficient.

---

## Important Findings (Should Fix)

### 4. Power iteration: 6 → 20 iterations (Agent 1)

For typical calibration data (tight cluster, λ₂/λ₁ ≈ 2×10⁻⁵), 6 iterations is overkill. But if the sensor moves mid-collection, eigenvalue ratio degrades to 0.1-0.5. At ratio 0.5, error after 6 iterations ≈ 1.5% — marginal for calibration.

20 iterations costs <1 µs on modern Android CPU. Negligible cost, strong safety margin.

**Fix applied:** Changed from 6 to 20 iterations.

### 5. ACC magnitude range too wide (Agent 2)

Original: 9.0-11.0 m/s² (±1.2 m/s² from gravity). WT901 noise+drift: ±0.4 m/s². The range is ~25× wider than needed.

**Fix applied:** Tightened to 9.3-10.3 m/s² (±0.5 m/s² ≈ ±0.05g). Still accommodates noise, drift, and small tilt, but rejects real motion.

### 6. Unit verification confirmed correct (Agent 2)

- `ImuSample.gyroX/Y/Z`: °/s (parser: `SCALE_GYRO = 2000f / 32768f`)
- `ImuSample.accX/Y/Z`: m/s² (parser: `SCALE_ACC = 16f * 9.80665f / 32768f`)
- Thresholds match. No conversion needed.

---

## Architecture Findings (Agent 3)

### 7. SharedFlow handoff is safe

`bleRepository.imuSamples` uses `MutableSharedFlow(extraBufferCapacity=1024)`. Multiple collectors (calibration + preview) each get their own copy. No data loss or interference.

### 8. MutableList race condition in CalibrateSensorUseCase

`leftSamples` / `rightSamples` are `MutableList<ImuSample>` written from SharedFlow collector. If the coroutine structure uses `coroutineScope` (not `supervisorScope`), a failure in one child cancels the other — potentially leaving partial data.

**Recommendation:** Use `supervisorScope` so one sensor failure doesn't cancel the other. Consider `CompletableDeferred` instead of shared `var` for warmup state tracking.

### 9. Per-sensor StateFlow for preview

Current preview uses `sample(100L)` on the shared flow, which can mix left/right delays. Consider per-sensor StateFlow for more predictable preview updates.

---

## Testing Findings (Agent 4)

### 10. Test framework is JUnit 4 + MockK, not JUnit 5

Spec originally said JUnit 5. Project uses JUnit 4 (`@Test`, `@Before`, `@After`) with MockK for mocking. Updated spec.

### 11. 19 tests designed across 4 categories

**Eigendecomposition (6 tests):**
- Known quaternion cluster → correct mean (0.1° tolerance)
- Hemisphere flip: alternating signs → same hemisphere
- Off-diagonal values not halved
- Power iteration: known matrix → correct eigenvector
- Power iteration: near-orthogonal init → still converges
- Single sample → returns that sample

**Still-detection (5 tests):**
- Gyro ≤ 5°/s accepted, > 5°/s rejected
- Acc 9.3-10.3 accepted, outside rejected
- MIN_STILL_SAMPLES: < 50 → failure
- MIN_STILL_SAMPLES: ≥ 50 → success
- Both sensors must meet minimum

**Integration (4 tests):**
- Full calibration cycle with mocked BLE
- One sensor fails → other succeeds (supervisorScope)
- Zero still samples → descriptive error
- Repeated calibration → stable results

**Property-based (4 tests):**
- Mean quaternion is unit length
- Mean quaternion is in same hemisphere as input
- More samples → more stable mean (variance decreases)
- Matrix M is symmetric positive semi-definite

### 12. Private method testing via reflection

`computeMeanQuaternion` and `dominantEigenvector4x4` are private. Test via:
- Reflection (`javaClass.getDeclaredMethod`, `isAccessible = true`)
- Or make them `internal` with `@VisibleForTesting`

---

## BLE Protocol Findings (Agent 5)

### 13. Quaternion format confirmed: w, x, y, z

Wt901Parser frame 0x59 parses q0, q1, q2, q3 where q0=w, q1=x, q2=y, q3=z (WitMotion convention confirmed by FAQ and reference implementation vruback/WT901BLECL).

### 14. SCALE_QUAT = 1/32768

Quaternion components are int16 scaled by 1/32768. Input precision ≈ 15 bits.

### 15. CRITICAL: App uses 0x61 Euler-derived quaternions, not native 0x59 quaternion frames

The WT901 supports two quaternion paths:

| Path | Frame | Source | Quality |
|------|-------|--------|---------|
| **Native** | 0x59 | Sensor's internal Kalman filter | High — directly from IMU fusion |
| **Euler-derived** | 0x61 | Roll/Pitch/Yaw → `eulerToQuaternion()` | Lower — conversion error + gimbal risk |

**Current state:** `BleManager.kt` only sends `setRate(0x09)` on connect — it does NOT configure the RSW register (0x02) to enable native quaternion output. All quaternions are derived from Euler angles in 0x61 combined frames.

**Impact on calibration:** The calibration operates on lower-quality Euler-derived quaternions. This introduces:
- Floating-point trig errors in `eulerToQuaternion()` (output not normalized)
- Potential gimbal lock at extreme angles
- Loss of the sensor's internal quaternion filter accuracy

**Recommendation:** Enable native 0x59 quaternion streaming by writing the RSW register in the BLE connect sequence. This is a **separate** fix from the calibration quality spec but should be prioritized.

### 16. `eulerToQuaternion()` does not normalize output

`Wt901Parser.kt:337-358` returns unnormalized quaternion from trig computation. This means all 0x61-derived quaternions may have |q| ≠ 1 by floating-point error. The calibration mean-normalization step compensates, but individual samples are slightly off-unit.

**Recommendation:** Add normalization after `eulerToQuaternion()`.

---

## Float32 vs Double Analysis (Agent 1)

Float32 is **sufficient** for this application:
- Input precision: 15 bits (WT901 int16 / 32768)
- Matrix M elements reach ~1000 for N=1000. Float32 ULP at 1000 ≈ 6×10⁻⁵
- Smallest meaningful signal (off-diagonal from 0.5° noise): ~4. Well above ULP.
- Second eigenvalue λ₂ ≈ 0.02. Safely above float32 rounding noise.
- Dominant eigenvector well-separated from noise subspace.

**Verdict:** Keep Float. Double adds marginal benefit for 15-bit input.

---

## Summary of Changes Applied to Spec

| Change | Agent Source | Priority |
|--------|-------------|----------|
| Remove `mXY /= 2f` (use symmetric aliases) | 1, 2 | Critical |
| Init power iteration with first sample | 1 | High |
| Increase iterations 6 → 20 | 1 | Medium |
| Tighten ACC range 9.0-11.0 → 9.3-10.3 | 2 | Medium |
| Add MIN_STILL_SAMPLES = 50 | 2 | High |
| Correct test framework JUnit 5 → JUnit 4 | 4 | Low |
| Add off-diagonal correctness test | 1 | High |
| Add MIN_STILL_SAMPLES boundary test | 2 | Medium |
| Document hemisphere flip redundancy for Markley | 1 | Low |
| Add unit verification note | 2 | Medium |
| Add Markley reference | 1 | Low |
| Enable native 0x59 quaternion streaming | 5 | High (separate PR) |
| Normalize `eulerToQuaternion()` output | 5 | Medium (separate PR) |

## Out-of-Scope Items (Separate PRs)

These findings are important but outside the calibration quality fixes scope:

1. **Enable native quaternion streaming (0x59)** — requires BLE protocol changes (RSW register write). Separate PR.
2. **Normalize `eulerToQuaternion()`** — parser fix, not calibration. Separate PR.
3. **Per-sensor StateFlow for preview** — UI improvement, not calibration. Separate PR.
4. **supervisorScope + CompletableDeferred** — coroutine structure improvement. Can be bundled with calibration fix if convenient.