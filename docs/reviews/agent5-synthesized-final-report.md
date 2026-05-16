# Synthesized Final Report: WT901 BLE Parser & Battery Fix

> Agent 5 (Synthesizer) — 2026-05-16
> Sources: Agent 1 (Wt901Parser), Agent 2 (BleManager/SharedFlow), Agent 3 (Reference App), Agent 4 (BleRepositoryImpl), original spec, WT901BLECL source code (`/tmp/WT901BLECL`), WitMotion official datasheet (PDF).

---

## 1. Executive Summary

**Top 5 Findings:**

1. **The spec missed a critical fourth parser bug:** 0x71 frames must skip checksum validation. Without this fix, the parser will reject every 0x71 frame after the frame size fix, because `isChecksumValid()` treats byte 10 as a checksum when it is actually data (`d3L`).
2. **The spec's battery voltage unit assumption is wrong.** The spec assumed register 0x64 returns "millivolts / 100" (e.g., 384 = 3.84V). The WT901BLECL reference app uses the raw value directly with thresholds 680-850 and does NO multiplication. The unit is unverified — likely centivolts (2S LiPo) or raw ADC counts.
3. **All 5 original bugs are real and confirmed** by both the reference app source code and the WitMotion datasheet. The root cause analysis is correct.
4. **Register reads coexist safely with IMU streaming** — no pause, no queue needed. The parser's ring buffer handles interleaved 0x61/0x71 frames correctly once the frame size and checksum bugs are fixed.
5. **A benign race condition exists** when `readBattery()` and `readBatteryMv()` are called concurrently (both read register 0x64). Both send commands and both receive identical responses, so the race is harmless. A per-address Mutex is recommended as a defensive follow-up.

**Overall Assessment:** The original spec correctly identified 5 bugs but missed the checksum bug and made an unverified assumption about the battery voltage unit. After incorporating these corrections, the implementation plan is sound and high-confidence.

---

## 2. Consensus Findings (All Agents Agree)

| Finding | Confidence | Evidence |
|---------|-----------|----------|
| 0x71 frame size is 20 bytes, not 11 | **Certain** | Reference app `Data.java` checks `packBuffer.length == 20`; datasheet Section 6.1.2 |
| 0x71 data starts at offset 4, 8 shorts | **Certain** | Reference app reads `fData[i]` from `packBuffer[i * 2 + 4]` for i=0..7 |
| 0x71 register address is at `buffer[2]` | **Certain** | Reference app `switch(packBuffer[2])`; datasheet format diagram |
| 0x71 has no checksum in BLE mode | **Certain** | Reference app has no checksum check; datasheet 20-byte format has no checksum byte |
| Battery register is 0x64, not 0x04 | **Certain** | Reference app `Constants.java`: `cell = new byte[]{0xff, 0xaa, 0x27, 0x64, 0x00}` |
| Register reads interleave with 0x61 streaming | **Certain** | Reference app sends reads continuously while streaming; same FFE4 characteristic |
| Parser buffer handles interleaved frames | **Certain** | `Wt901Parser.feed()` appends bytes and parses in a loop |
| `readBattery()` uses wrong register and wrong conversion | **Certain** | Code reads 0x04 (baud) and clamps with `coerceIn(0, 100)` |

---

## 3. Conflicts & Resolutions

### Conflict 1: Battery Voltage Unit and Conversion Table

**Original spec:** Assumes register 0x64 returns "millivolts / 100" (384 = 3.84V = 3840mV). Provides a single-cell Li-ion conversion table: 3960mV = 100%, 3930mV = 90%, etc.

**Agent 1:** Calls the conversion table "not verified" and says it "should be verified against WitMotion official documentation, the reference app, real device measurements."

**Agent 2:** Does not deeply analyze the voltage unit.

**Agent 3:** Identifies that the reference app uses raw values with thresholds 680, 735, 745, 775, 850 and hypothesizes these are **2S LiPo centivolts** (6.80V-8.50V). Explicitly recommends: "Do NOT multiply by 100 until hardware test confirms unit."

**Agent 4:** Reviewed the `voltageToPercent()` approach and conversion table.

**Resolution — VERDICT:**

The spec's "millivolts / 100" claim is **unsubstantiated**. No source is cited, and the WitMotion official datasheet does NOT document register 0x64 at all (the register table ends at 0x54). The reference app is our **only ground truth** for this register.

The reference app uses `fData[0]` **raw** with thresholds 680-850. These thresholds are **inconsistent** with single-cell Li-ion millivolts/100 (which would be ~300-420 for a 3.0-4.2V range). The most physically coherent explanation is **2S LiPo measured in centivolts** (0.01V), but the module datasheet states "working voltage 3.3V~5V" which favors a single-cell configuration with a voltage divider feeding an ADC.

**Because the unit is unverified, the implementation must:**
- Treat register 0x64 as an opaque raw integer
- Use the **reference app's thresholds directly** for percentage mapping
- **Do NOT multiply by 100**
- Add a TODO comment and a hardware verification task

This approach is the safest because it matches the behavior of the only working implementation we have (the reference app).

### Conflict 2: Should We Add a Mutex for Concurrent Register Reads?

**Agent 1:** Identifies a "real bug" where concurrent coroutines calling `readRegisterResponse(sensorId, 0x64)` race for the same SharedFlow emission. Mentions it but does not strongly recommend a Mutex as P0.

**Agent 2:** Strongly recommends adding a per-address `Mutex` in `BleManager.readRegisterResponse()` to serialize register reads per sensor.

**Agent 3:** Notes the reference app has no application-level queue or mutex and uses fire-and-forget writes. Acknowledges our suspend function model is a better abstraction.

**Resolution — VERDICT:**

The race condition is **real but benign** for the specific case of `readBattery()` + `readBatteryMv()` (both read 0x64, both send commands, both receive identical responses). For `ReadSensorInfoUseCase` (4 concurrent reads of different registers), the SharedFlow with distinct predicates works correctly because each collector filters by a different register address.

A per-address `Mutex` is a good **defensive measure** but not critical for the immediate fix. It adds serialization overhead that the reference app doesn't have. **Recommendation:** Implement as P2 (follow-up) after the parser fix is verified.

### Conflict 3: Checksum for 0x71 Frames

**All agents agree:** Skip checksum validation for 0x71. No conflict. This is the most critical missing bug.

---

## 4. Critical New Bug: Checksum Validation for 0x71

### The Problem

Current `Wt901Parser.kt` validation logic (lines 169-180):

```kotlin
if (frameType == TYPE_COMBINED) {
    if (!isCombinedFramePlausible()) { ... }
} else if (!isChecksumValid()) {
    shiftBuffer(1)
    continue
}
```

`isChecksumValid()` sums bytes `0..9` and compares against `buffer[10]`. It hardcodes `INDIVIDUAL_FRAME_SIZE = 11`, so it always checks `buffer[0..9]` vs `buffer[10]`.

When `frameSize = 20` for 0x71 (after the spec fix), `isChecksumValid()` still reads `buffer[10]` as if it were a checksum. But in a 20-byte 0x71 frame, byte 10 is `d3L` — the low byte of data[3], part of the register read payload. The checksum check will virtually always fail, causing the parser to `shiftBuffer(1)` and enter desync recovery. **The 0x71 responses will still never reach `readRegisterResponse()`.**

### Evidence

- **Reference app:** `Data.java` has NO checksum validation for any frame type. It simply parses based on `packBuffer[1]`.
- **Datasheet:** The 20-byte BLE 0x71 format diagram shows no checksum byte. The full 20 bytes are: header (2) + register address (2) + data (16).
- **Parser code:** `isChecksumValid()` uses `INDIVIDUAL_FRAME_SIZE - 1 = 10`, which is hardcoded for 11-byte individual frames (0x51/0x52/0x59).

### Required Fix

Add `TYPE_REG_READ` to the "no checksum" branch:

```kotlin
when (frameType) {
    TYPE_COMBINED -> {
        if (!isCombinedFramePlausible()) {
            Log.w(logTag, "0x61 frame failed plausibility check — desync likely, skipping 1 byte")
            shiftBuffer(1)
            continue
        }
    }
    TYPE_REG_READ -> {
        // 0x71 frames in BLE mode have no checksum
    }
    else -> {
        if (!isChecksumValid()) {
            shiftBuffer(1)
            continue
        }
    }
}
```

**Without this fix, the entire parser fix is ineffective — 0x71 frames will still be dropped.**

---

## 5. Voltage Unit Resolution

### The Question

What unit does register 0x64 return? Millivolts? Centivolts? Raw ADC counts?

### Evidence from Reference App

**`Data.java` (line 113):**
```java
case 0x64:
    battery = fData[0];  // fData[0] is raw int16 from bytes 4-5, stored as float
```

**`DeviceControlActivity.java` (lines 618-634):**
```java
if (data.getBattery() < 680) { /* cell1 */ }
if (data.getBattery() >= 680 && data.getBattery() < 735) { /* cell2 */ }
if (data.getBattery() >= 745 && data.getBattery() < 775) { /* cell3 */ }
if (data.getBattery() >= 775 && data.getBattery() < 850) { /* cell4 */ }
if (data.getBattery() >= 850) { /* cell5 */ }
```

**Critical observations:**
1. No multiplication by 100. The raw value IS the value used for threshold comparison.
2. Thresholds: 680 (empty/low), 850 (full).
3. Gap between 735 and 745 (reference app bug).

### Evidence from Official Datasheet

- Register 0x64 is **NOT in the official WitMotion register table** (table ends at 0x54, Q3 quaternion).
- The module has a "self-contained battery" and "working voltage 3.3V~5V".
- There is an LDO voltage regulator on board.

### Analysis

The spec's claim "register value = millivolts / 100" is **unsubstantiated**. If it were true, a single-cell Li-ion battery (3.0V-4.2V) would produce values of 300-420, which is far below the reference app's thresholds of 680-850.

**Hypothesis 1: 2S LiPo, centivolts (0.01V)**
- 680 = 6.80V (empty), 850 = 8.50V (full)
- Fits the thresholds perfectly
- But contradicts datasheet "working voltage 3.3V~5V"

**Hypothesis 2: Single-cell Li-ion, raw ADC counts via voltage divider**
- Battery 3.0-4.2V measured through a resistive divider into a 10-bit ADC
- If 4.2V → ~850 counts, divider maps battery to ADC range
- Consistent with "working voltage 3.3V~5V" and single-cell battery
- The exact conversion depends on unknown ADC resolution and divider ratio

**Conclusion:** We cannot definitively determine the physical unit without hardware measurement (multimeter vs. register value). The reference app treats the value as an opaque integer with thresholds 680-850. **We must do the same.**

### Definitive Answer

**Register 0x64 returns an opaque raw integer.** The reference app uses thresholds 680, 735, 745, 775, 850 to map to 5 battery icon levels. Our app should use these same thresholds mapped to 0-100%:

```kotlin
private fun rawToPercent(raw: Int): Int = when {
    raw >= 850 -> 100
    raw >= 775 -> 80
    raw >= 745 -> 60
    raw >= 735 -> 40
    raw >= 680 -> 20
    else -> 0
}
```

**`readBatteryMv()` should return the raw value, NOT multiply by 100:**

```kotlin
override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt()  // Raw value — unit unverified, requires hardware test
    }
```

**A hardware verification task must be added to the backlog:** Connect a WT901BLECL sensor, read register 0x64, and compare the raw value to a multimeter reading of the battery terminals to determine the exact scale factor.

---

## 6. Updated Spec

Below is the complete corrected spec incorporating all findings from all agents.

---

### BLE Parser & Battery Fix Design (Updated)

**Goal:** Fix 6 bugs in WT901 BLE parser and battery reading that cause register reads to timeout and battery percentage to show 0%.

**Architecture:** Fix Wt901Parser's 0x71 frame handling (frame size, checksum skip, data offset) and BleRepositoryImpl's battery register and voltage-to-percent conversion.

**TechStack:** Kotlin, Android BLE, JUnit 5

---

#### Background

Device testing revealed:
- Battery percentage shows "Л:0% П:0%" for both sensors
- Logcat shows `readRegisterResponse: timeout for reg=0x68/0x60/0x4/0x64` during IMU streaming
- Reference app (WT901BLECL) successfully reads registers during streaming

Root cause: Wt901Parser treats 0x71 (register read response) frames as 11-byte individual frames, but BLE 0x71 frames are 20 bytes. This causes buffer desync — the parser reads 11 bytes, leaves 9 residual bytes, and subsequent frames can't be parsed. The 0x71 responses never reach `readRegisterResponse()`, causing timeouts.

Secondary bug: `readBattery()` reads register 0x04 (BAUD rate, not battery) and incorrectly interprets the result as a 0-100 percentage. The correct register is 0x64 (battery voltage). The unit of register 0x64 is **unverified** — the reference app uses raw values with thresholds 680-850.

---

#### Bug 1: 0x71 Frame Size

**File:** `mobile/app/src/main/java/ru/skatelab/capture/data/ble/Wt901Parser.kt`

**Current (broken):**
```kotlin
val frameSize = if (frameType == TYPE_COMBINED) COMBINED_FRAME_SIZE else INDIVIDUAL_FRAME_SIZE
// INDIVIDUAL_FRAME_SIZE = 11 — used for 0x71, but BLE 0x71 is 20 bytes
```

**Fix:** Add `REG_READ_FRAME_SIZE = 20` and check frame type:
```kotlin
val frameSize = when (frameType) {
    TYPE_COMBINED -> COMBINED_FRAME_SIZE
    TYPE_REG_READ -> REG_READ_FRAME_SIZE
    else -> INDIVIDUAL_FRAME_SIZE
}
```

---

#### Bug 2: Checksum Validation for 0x71

**File:** `Wt901Parser.kt`

**Current (broken):** `isChecksumValid()` is called for 0x71 frames. It sums bytes 0..9 and checks against byte 10. In a 20-byte 0x71 frame, byte 10 is data (`d3L`), not a checksum. This virtually always fails, causing desync.

**Fix:** Skip checksum validation for `TYPE_REG_READ`, same as `TYPE_COMBINED`:
```kotlin
when (frameType) {
    TYPE_COMBINED -> {
        if (!isCombinedFramePlausible()) {
            Log.w(logTag, "0x61 frame failed plausibility check — desync likely, skipping 1 byte")
            shiftBuffer(1)
            continue
        }
    }
    TYPE_REG_READ -> {
        // 0x71 frames in BLE mode have no checksum
    }
    else -> {
        if (!isChecksumValid()) {
            shiftBuffer(1)
            continue
        }
    }
}
```

**Critical:** Without this fix, 0x71 frames will still be dropped even after the frame size fix.

---

#### Bug 3: Data Offset and Length

**Current (broken):**
```kotlin
// parseRegisterReadFrame reads 3 shorts from buffer[3..8]
val register = buffer[2].toInt() and 0xFF
val data = shortArrayOf(
    ((buffer[3].toInt() and 0xFF) or (buffer[4].toInt() shl 8)).toShort(),
    ((buffer[5].toInt() and 0xFF) or (buffer[6].toInt() shl 8)).toShort(),
    ((buffer[7].toInt() and 0xFF) or (buffer[8].toInt() shl 8)).toShort(),
)
```

**Fix:** BLE 0x71 returns 8 consecutive register values (16 bytes of data). Data starts at offset 4:
```kotlin
val register = buffer[2].toInt() and 0xFF
val data = ShortArray(8) { i ->
    ((buffer[4 + i * 2].toInt() and 0xFF) or (buffer[5 + i * 2].toInt() shl 8)).toShort()
}
```

**Impact:** `RegisterReadResult.data` changes from `ShortArray(3)` to `ShortArray(8)`. All callers that access `data[0]` still work — they just get more data.

---

#### Bug 4: Battery Register

**File:** `BleRepositoryImpl.kt`

**Current (broken):**
```kotlin
override suspend fun readBattery(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x04)  // WRONG: 0x04 = BAUD rate
    return result.map { data ->
        data[0].toInt().coerceIn(0, 100)  // WRONG: not a percentage
    }
}
```

**Fix:**
```kotlin
override suspend fun readBattery(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)  // 0x64 = battery voltage
    return result.map { data ->
        rawToPercent(data[0].toInt())  // Use reference-app thresholds
    }
}

/**
 * Convert raw battery register value to percentage.
 * Thresholds are taken from the WT901BLECL reference app (DeviceControlActivity.java).
 * The physical unit of register 0x64 is unverified — may be centivolts or ADC counts.
 * TODO: Verify with hardware measurement (multimeter vs. register value).
 */
private fun rawToPercent(raw: Int): Int = when {
    raw >= 850 -> 100
    raw >= 775 -> 80
    raw >= 745 -> 60
    raw >= 735 -> 40
    raw >= 680 -> 20
    else -> 0
}
```

---

#### Bug 5: readBatteryMv

**File:** `BleRepositoryImpl.kt`

**Current:**
```kotlin
override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)
    return result.map { data ->
        data[0].toInt()  // Returns raw register value
    }
}
```

**Fix:** Return the raw value with a clear comment that the unit is unverified. Do NOT multiply by 100.
```kotlin
override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt()  // Raw value — unit unverified. TODO: compare with multimeter.
    }
```

---

#### Bug 6: Register Address Parsing

**Current:** `buffer[2]` is used as the register address.

**Verdict:** This is actually correct. BLE 0x71 format is `[0x55][0x71][RegL][RegH][d0L][d0H]...[d7L][d7H]`. `buffer[2]` = RegL, which is the register byte we want. No change needed.

---

#### Testing

- Update `Wt901ParserTest` to test 0x71 frames as 20-byte BLE format
- Add test for 0x71 checksumless parsing (arbitrary byte 10 should not cause failure)
- Add test for `rawToPercent()`
- Verify existing `parseRegisterReadResponseDoesNotInterfereWithImuCycle` still passes with 20-byte 0x71
- Add test for 0x71 interleaved with 0x61 in a single notification buffer

---

#### Files to Change

| File | Change |
|------|--------|
| `Wt901Parser.kt` | Add `REG_READ_FRAME_SIZE = 20`, fix frame size logic, **skip checksum for 0x71**, fix `parseRegisterReadFrame` data offset/length |
| `BleRepositoryImpl.kt` | Fix `readBattery` register 0x04→0x64, add `rawToPercent()` with reference-app thresholds, fix `readBatteryMv` (no *100) |
| `Wt901ParserTest.kt` | Update 0x71 test frames to 20-byte BLE format, add checksumless test, add interleaving test |
| `SensorInfo.kt` | No change needed (already has `batteryPercent` and `batteryMv`) |

---

## 7. Implementation Priority

| Priority | Task | File | Why P0? |
|----------|------|------|---------|
| **P0** | Fix 0x71 frame size to 20 bytes | `Wt901Parser.kt` | Without this, 0x71 frames desync |
| **P0** | Skip checksum for 0x71 frames | `Wt901Parser.kt` | Without this, frame size fix is ineffective |
| **P0** | Fix 0x71 data offset to 4, length to 8 shorts | `Wt901Parser.kt` | Wrong data extraction |
| **P0** | Fix battery register 0x04 → 0x64 | `BleRepositoryImpl.kt` | Reading wrong register entirely |
| **P0** | Use reference-app raw thresholds for battery % | `BleRepositoryImpl.kt` | Current conversion is completely wrong |
| P1 | Update tests for 20-byte 0x71 frames | `Wt901ParserTest.kt` | Tests must match new behavior |
| P1 | Fix `readBatteryMv` to return raw value | `BleRepositoryImpl.kt` | Remove unverified *100 multiplication |
| P2 | Add per-address Mutex for register reads | `BleManager.kt` | Defensive against race conditions |
| P2 | Use StateFlow for battery caching | `BleRepositoryImpl.kt` | Avoid redundant BLE reads |
| P2 | Hardware verify battery register unit | Device lab | Determine actual scale factor |

---

## 8. Parallel/Async Recommendations

### Final Verdict: Keep Current Approach, No Mutex Required for P0

The current `BleManager` design uses:
- `HandlerThread` (`workHandler`) for serialized GATT writes and parser feeding
- `MutableSharedFlow` with `extraBufferCapacity = 8` for register read results
- `withTimeoutOrNull(2000L)` for response awaiting

This design is **superior** to the reference app's fire-and-forget approach. The reference app has no response tracking — it just periodically fires reads and updates UI when responses happen to arrive. Our suspend function model with `first { predicate }` is a better fit for Kotlin coroutines.

### Register Read Parallelism Assessment

| Aspect | Status | Recommendation |
|--------|--------|----------------|
| Reads during streaming | **Fully supported** | Parser handles interleaved 0x61/0x71 correctly after fixes |
| Concurrent reads to same register | **Benign race** | Both send commands, both receive identical responses. No fix needed for P0. |
| Concurrent reads to different registers | **Works correctly** | SharedFlow predicates filter by register address. Each collector gets its matching response. |
| Timeout under streaming load | **Possible but unlikely** | 2-second timeout is generous. If timeouts occur, increase to 3000ms. |
| Queue pressure | **Acceptable** | `HandlerThread` serializes writes. Android BLE stack serializes per connection. |

### Recommendation: No Mutex for P0

Adding a Mutex per sensor would serialize the 4 concurrent reads in `ReadSensorInfoUseCase`, turning ~50ms parallel reads into ~200ms serial reads. This is unnecessary because:
1. The SharedFlow predicates already isolate responses by register address
2. The BLE stack serializes writes anyway
3. The race for identical-register reads is benign (both get the same data)

**If post-deployment telemetry shows register read timeouts, THEN add a Mutex as a defensive measure.**

### Recommended: Read Sensor Info Once on Connect

`ReadSensorInfoUseCase` currently reads device ID, firmware, battery %, and battery mV when the user starts recording. At this point, IMU streaming is already active at high rate.

**Better approach:** Read device ID, firmware, and initial battery level **immediately after connection** (in `BleManager`'s `onConnectionStateChange(STATE_CONNECTED)` handler), before streaming starts. Cache these values. During recording, only poll battery periodically (every 30s).

This avoids register reads during the highest BLE notification load and gives the user battery info immediately upon connection.

---

## Appendix: Reference App Command Summary

Commands the WT901BLECL reference app sends:

**On connect:**
```
FF AA 27 64 00   // read battery (0x64)
FF AA 27 68 00   // read device ID (0x68)
FF AA 03 09 00   // setRate(0x09) — after 1s delay
```

**Periodic (every 5 seconds):**
```
FF AA 27 68 00   // read device ID
FF AA 27 64 00   // read battery
```

**UI refresh thread (every 240ms, data-type dependent):**
```
FF AA 27 40 00   // read angle
FF AA 27 3A 00   // read magnetometer
FF AA 27 45 00   // read pressure
FF AA 27 41 00   // read port
FF AA 27 51 00   // read quaternion
```

**Battery thresholds (from `DeviceControlActivity.java`):**
```java
< 680        → cell1 (empty)
680-734      → cell2 (gap at 735-744 is a reference app bug)
745-774      → cell3
775-849      → cell4
>= 850       → cell5 (full)
```

---

*Report saved to: `/home/michael/Github/skating-biomechanics-ml/.claude/worktrees/android-app/docs/reviews/agent5-synthesized-final-report.md`*
