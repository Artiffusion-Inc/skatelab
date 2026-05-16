# Agent 1 Review: WT901 BLE Parser 0x71 Frame Fix

## Executive Summary

The spec correctly identifies the root cause (0x71 frame size = 11 is wrong; it must be 20 bytes) and the correct data layout. However, **the spec misses a critical fourth parser bug**: 0x71 frames must skip checksum validation. Without that fix, the parser will reject every 0x71 frame after shifting to `frameSize = 20`, because `isChecksumValid()` treats byte 10 as a checksum when it is actually data.

## 1. Spec Correctness Assessment (Bugs 1-3)

### 1.1 Bug 1: 0x71 Frame Size — CONFIRMED CORRECT

The WT901BLECL datasheet (Section 6.1.2) states:

> "After send instruction, the module turn back a data packet 0x55 0x71. There are register address and 7 registers data (Fixed upload 8 registers). Return data format as below: Start register(2 byte) + register data(16 byte, 8 registers)"

The example for magnetic field read shows:
```
55 71 3A 00 68 01 69 00 7A 00 00 00 00 00 00 00 00 00 00 00 Total: 20 bytes.
```

Layout confirmed:
- Byte 0: `0x55` header
- Byte 1: `0x71` type
- Byte 2: `RegL` (start register low byte)
- Byte 3: `RegH` (start register high byte)
- Bytes 4-19: 8 consecutive register values (16 bytes, little-endian int16)

**Verdict:** Adding `REG_READ_FRAME_SIZE = 20` is correct.

### 1.2 Bug 2: Register Address Parsing — CONFIRMED CORRECT (no change needed)

`buffer[2]` is indeed `RegL`. The spec correctly concludes no change is needed.

### 1.3 Bug 3: Data Offset and Length — CONFIRMED CORRECT

Current code reads 3 shorts starting at offset 3:
```kotlin
val data = ShortArray(3) { i -> readInt16LEShort(3 + i * 2) }
```

The correct layout has data starting at offset 4 (after `RegH`), with 8 shorts:
```kotlin
val data = ShortArray(8) { i -> readInt16LEShort(4 + i * 2) }
```

**Verdict:** The proposed fix is correct.

---

## 2. Critical Missing Bug: Checksum Validation on 0x71 Frames

### The Problem

Current validation logic in `Wt901Parser.kt` (lines 169-180):
```kotlin
if (frameType == TYPE_COMBINED) {
    if (!isCombinedFramePlausible()) { ... }
} else if (!isChecksumValid()) {
    shiftBuffer(1)
    continue
}
```

`isChecksumValid()` sums bytes `0..9` and compares against `buffer[10]`:
```kotlin
private fun isChecksumValid(): Boolean {
    var sum = 0
    for (i in 0 until INDIVIDUAL_FRAME_SIZE - 1) {
        sum += buffer[i].toInt() and 0xFF
    }
    return (sum and 0xFF) == (buffer[INDIVIDUAL_FRAME_SIZE - 1].toInt() and 0xFF)
}
```

This hardcodes `INDIVIDUAL_FRAME_SIZE = 11`, so it always checks `buffer[0..9]` vs `buffer[10]`.

With the proposed fix (`frameSize = 20` for 0x71), the frame is 20 bytes but `isChecksumValid()` still reads `buffer[10]` as if it were a checksum. Byte 10 of a 0x71 frame is `d3L` (data byte 3 low) — part of the register data. The checksum check will virtually always fail, causing the parser to `shiftBuffer(1)` and enter desync recovery.

### The Datasheet Evidence

The datasheet explicitly mentions checksum only for individual frames (0x51/0x52/0x59) and quaternion frames. For 0x71, the format diagram shows no checksum byte — the full 20 bytes are header (2) + register address (2) + data (16).

### Required Fix

Add `TYPE_REG_READ` to the "no checksum" branch:
```kotlin
if (frameType == TYPE_COMBINED || frameType == TYPE_REG_READ) {
    // No checksum for combined or register-read frames
    if (frameType == TYPE_COMBINED && !isCombinedFramePlausible()) { ... }
} else if (!isChecksumValid()) {
    shiftBuffer(1)
    continue
}
```

Or more explicitly:
```kotlin
when (frameType) {
    TYPE_COMBINED -> {
        if (!isCombinedFramePlausible()) {
            shiftBuffer(1)
            continue
        }
    }
    TYPE_REG_READ -> {
        // No checksum or plausibility check for 0x71
    }
    else -> {
        if (!isChecksumValid()) {
            shiftBuffer(1)
            continue
        }
    }
}
```

**Without this fix, the entire spec is ineffective — 0x71 frames will still be dropped.**

---

## 3. Buffer Management Edge Cases

### 3.1 Split 0x71 Across Notifications

The datasheet states: "Bluetooth uploads up to 20 bytes per data." A 0x71 frame is exactly 20 bytes, so it typically fits in a single BLE notification. However, the parser must handle fragmentation defensively.

With `frameSize = 20`, the `while (bufferSize >= frameSize)` loop correctly waits until all 20 bytes arrive. The `appendToBuffer` accumulates bytes across notifications. This is safe.

**Recommendation:** Add a test case where a 0x71 frame is split across two notifications (e.g., 12 bytes + 8 bytes).

### 3.2 0x71 Interleaved with 0x61

Yes, 0x71 and 0x61 frames can and will interleave in the BLE notification stream. The sensor continuously streams 0x61 at the configured rate (e.g., 100Hz). When a register read command is sent, the sensor replies with 0x71 over the same notification characteristic.

Example byte stream:
```
[0x61 frame 1: 20 bytes][0x71 frame: 20 bytes][0x61 frame 2: 20 bytes]
```

With the corrected frame size logic, the parser handles this correctly:
1. Sees `0x55 0x61` → frameSize = 20 → parses combined frame
2. Sees `0x55 0x71` → frameSize = 20 → parses register read frame
3. Sees `0x55 0x61` → frameSize = 20 → parses combined frame

**But only if the checksum bug is also fixed.** Otherwise step 2 fails and causes desync.

### 3.3 Residual Bytes After 0x71

If the buffer contains exactly 20 bytes of 0x71, after parsing and `shiftBuffer(20)`, `bufferSize` becomes 0. The while loop exits safely. No residual corruption.

If a 0x71 frame is followed by a partial 0x61 in the same notification:
```
[0x71: 20 bytes][0x61 first 10 bytes]
```
After parsing 0x71, 10 bytes remain. The while loop checks `bufferSize >= frameSize` (10 < 20 for 0x61), breaks, and waits for the next notification. This is correct.

### 3.4 False 0x55 in 0x71 Payload

The 0x71 data payload can contain `0x55`. Example: a register value of `0x55 0x00` = 85 decimal. The parser's `findFrameHeader()` scans for the first `0x55`. If data byte 0 happens to be `0x55`, the parser could misinterpret it as a frame start.

However, the parser first checks `buffer[1]` for the frame type. If `buffer[1]` is not a known type (0x51, 0x52, 0x59, 0x61, 0x71), it falls to the `else` branch and `shiftBuffer(1)`. Then it finds the real header. This is a well-known recovery mechanism.

But with the checksum bug unfixed, a false header inside 0x71 data followed by an accidental "valid" checksum could cause misalignment. This is extremely unlikely but theoretically possible.

**Recommendation:** Consider a more robust framing strategy in future: validate that `buffer[1]` is a known type BEFORE committing to a frame size. The current code does this correctly.

---

## 4. Trace: `parse()` → Callback → SharedFlow → `readRegisterResponse()`

### Flow Verification

1. **BLE notification arrives**: `onCharacteristicChanged()` in `BleManager.kt` (line 377)
2. **Immediate copy**: `val bytes = characteristic.value.copyOf()` (line 385) — critical, because the BLE stack reuses the underlying buffer
3. **Posted to work thread**: `workHandler.post { ... parser.feed(bytes, arrivalNs) ... }` (line 396)
4. **Parser parses 0x71**: `parseRegisterReadFrame()` calls `onRegisterRead?.invoke(...)` (line 421 in parser)
5. **Callback emits to SharedFlow**: In `BleManager`, `onRegisterRead = { result -> _registerReadResults.tryEmit(address to result) }` (line 401-403)
6. **Collector receives**: `readRegisterResponse()` uses `withTimeoutOrNull(timeoutMs) { _registerReadResults.first { addr == address && r.register == register }.second }` (lines 510-516)

### Assessment

- The flow is **architecturally correct**.
- `_registerReadResults` has `extraBufferCapacity = 8`, so up to 8 unmatched register read results are buffered. This is sufficient.
- `first()` with a predicate correctly skips results for other sensors or other registers.
- `withTimeoutOrNull(2000L)` gives a 2-second window, which is ample for BLE round-trip.

### Race Condition: Concurrent Register Reads

If two coroutines concurrently call `readRegisterResponse(sensorId, 0x64)`, both will listen to `_registerReadResults`. Whichever `first()` predicate matches first will consume the result. The other coroutine will timeout.

**This is a real bug in concurrent usage.** The `BleRepositoryImpl` does not serialize register reads per sensor.

### Impact on IMU Streaming

`readRegisterResponse()` is a suspend function — it suspends the caller coroutine, not a thread. IMU parsing continues on `workHandler` independently. There is no thread blocking.

However, the `writeBytes()` call is posted to `workHandler`, which is the same thread doing parsing. If `workHandler` has a backlog of parsing tasks, the write might be delayed. In practice, GATT writes are fast and the HandlerThread message queue is not a bottleneck.

---

## 5. Parallel Register Read Feasibility

### Current State: Partially Non-Blocking

Register reads already do not block IMU streaming. The parser and BLE callbacks run on `workHandler`; the caller coroutine suspends on `first()`. IMU samples continue to flow through `_imuSamples`.

### Can We Make Register Reads More Parallel?

Yes, but with caveats:

1. **Background battery polling**: A coroutine could call `readRegisterResponse(0x64)` every 30 seconds. This works today but risks the race condition mentioned above.

2. **Per-sensor register read queue**: Add a `Mutex` or `Channel` per sensor in `BleRepositoryImpl` to serialize register reads:
   ```kotlin
   private val registerLocks = ConcurrentHashMap<SensorId, Mutex>()
   
   override suspend fun readBattery(sensorId: SensorId): Result<Int> {
       val lock = registerLocks.getOrPut(sensorId) { Mutex() }
       return lock.withLock {
           // ... read register
       }
   }
   ```

3. **Dedicated battery polling coroutine**: Instead of on-demand reads, `BleManager` could run a `CoroutineScope` job that periodically reads battery and publishes to a `StateFlow`. This decouples UI from reads entirely.

### Thread Safety of Parser ByteBuffer

The parser's `buffer` (a `ByteArray`) and `bufferSize` are instance fields with no synchronization. However, `BleManager` guarantees single-threaded access:
- One `Wt901Parser` instance per BLE device
- `feed()` is called only from `workHandler` (a `HandlerThread`)

Therefore, no additional synchronization is needed for the parser itself. But this is an implicit contract — if future code calls `feed()` from a different thread, it will corrupt the buffer.

---

## 6. Additional Bugs and Concerns Found

### 6.1 `readBattery()` Uses Wrong Register (0x04 = BAUD)

Confirmed in `BleRepositoryImpl.kt` line 83-88:
```kotlin
override suspend fun readBattery(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x04)  // WRONG: 0x04 = BAUD rate
    return result.map { data ->
        data[0].toInt().coerceIn(0, 100)  // WRONG: not a percentage
    }
}
```

The spec correctly identifies this. Fix to 0x64 and add `voltageToPercent()`.

### 6.2 `readBatteryMv()` Returns Raw Register Value, Not Millivolts

Confirmed in `BleRepositoryImpl.kt` line 115-119:
```kotlin
override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt() and 0xFFFF  // Missing * 100
    }
```

The spec correctly identifies this. Must multiply by 100.

### 6.3 `readChipTime()` Reads Register 0x50, Which Is "KEEP" in BLE Datasheet

In the WT901BLECL datasheet register table, 0x50 is listed as "KEEP" (reserved). However, the code reads it as if it contains chip time. This may work on some firmware versions but is not documented. The time registers are 0x30-0x33.

**Recommendation:** Verify with the actual device or reference app whether 0x50 is valid for chip time on the WT901BLECL variant.

### 6.4 `readDeviceId()` and `readFirmwareVersion()` Use Undocumented Registers

- 0x68 (device ID) and 0x60 (firmware version) are not in the standard WT901BLECL register table (which ends at 0x54).
- These might be extended registers specific to newer firmware or different variants.
- The code assumes 3 shorts of data (`data[0]`, `data[1]`, `data[2]`). After the fix (8 shorts), this will still work — the extra data is simply ignored.

### 6.5 Tests Use 11-Byte 0x71 Frames

`Wt901ParserTest.kt`:
- `parseRegisterReadResponse()` builds an 11-byte frame via `buildFrame(0x71, data)`
- `parseRegisterReadResponseDoesNotInterfereWithImuCycle()` does the same

These tests pass with the broken code but do not represent the real BLE protocol. After the fix, they must be rewritten to construct 20-byte 0x71 frames without checksums.

### 6.6 `voltageToPercent()` Conversion Table Not Verified

The spec provides a voltage-to-percentage conversion table:
```kotlin
private fun voltageToPercent(mv: Int): Int = when {
    mv >= 3960 -> 100
    mv >= 3930 -> 90
    ...
}
```

There is no source cited for this table. It should be verified against:
- WitMotion official documentation
- The reference app (WT901BLECL)
- Real device measurements

If the table is inaccurate, users will see incorrect battery percentages.

---

## 7. Specific Code Recommendations

### 7.1 `Wt901Parser.kt` Changes

```kotlin
companion object {
    // ... existing constants ...
    private const val REG_READ_FRAME_SIZE = 20
}

// In feed():
val frameSize = when (frameType) {
    TYPE_COMBINED -> COMBINED_FRAME_SIZE
    TYPE_REG_READ -> REG_READ_FRAME_SIZE
    else -> INDIVIDUAL_FRAME_SIZE
}

// In validation section:
when (frameType) {
    TYPE_COMBINED -> {
        if (!isCombinedFramePlausible()) {
            Log.w(logTag, "0x61 frame failed plausibility check — desync likely, skipping 1 byte")
            shiftBuffer(1)
            continue
        }
    }
    TYPE_REG_READ -> {
        // 0x71 frames have no checksum; data occupies full 20 bytes
    }
    else -> {
        if (!isChecksumValid()) {
            shiftBuffer(1)
            continue
        }
    }
}

// In parseRegisterReadFrame():
private fun parseRegisterReadFrame() {
    val reg = buffer[2].toInt() and 0xFF
    val data = ShortArray(8) { i -> readInt16LEShort(4 + i * 2) }
    onRegisterRead?.invoke(RegisterReadResult(reg, data))
}
```

### 7.2 `Wt901ParserTest.kt` Changes

Replace 11-byte 0x71 frame construction with 20-byte BLE format:

```kotlin
private fun buildRegReadFrame(register: Int, dataValues: ShortArray): ByteArray {
    require(dataValues.size == 8) { "BLE 0x71 requires exactly 8 shorts (16 bytes) of data" }
    val frame = ByteArray(20)
    frame[0] = 0x55.toByte()
    frame[1] = 0x71.toByte()
    frame[2] = (register and 0xFF).toByte()
    frame[3] = ((register shr 8) and 0xFF).toByte()
    for (i in 0 until 8) {
        val offset = 4 + i * 2
        frame[offset] = (dataValues[i].toInt() and 0xFF).toByte()
        frame[offset + 1] = (dataValues[i].toInt() shr 8 and 0xFF).toByte()
    }
    return frame
}
```

Update tests to use `buildRegReadFrame` and verify 8 shorts.

### 7.3 `BleRepositoryImpl.kt` Changes

```kotlin
override suspend fun readBattery(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)
    return result.map { data ->
        voltageToPercent(data[0].toInt() * 100)
    }
}

override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt() * 100
    }

private fun voltageToPercent(mv: Int): Int = when {
    mv >= 3960 -> 100
    mv >= 3930 -> 90
    mv >= 3870 -> 75
    mv >= 3820 -> 60
    mv >= 3790 -> 50
    mv >= 3770 -> 40
    mv >= 3730 -> 30
    mv >= 3700 -> 20
    mv >= 3680 -> 15
    mv >= 3500 -> 10
    mv >= 3400 -> 5
    else -> 0
}
```

### 7.4 Add Tests for Edge Cases

1. **0x71 split across two notifications**
2. **0x71 interleaved with 0x61 frames**
3. **False 0x55 inside 0x71 payload**
4. **Partial 0x71 at end of buffer followed by complete frame in next notification**
5. **Concurrent register reads** (integration test)

---

## 8. Summary Table

| Issue | Spec Coverage | Verdict | Required Action |
|-------|--------------|---------|-----------------|
| 0x71 frame size = 20 | Yes | Correct | Implement |
| Register address at `buffer[2]` | Yes | Correct | No change |
| Data offset = 4, length = 8 shorts | Yes | Correct | Implement |
| **Skip checksum for 0x71** | **No** | **Critical omission** | **Add to spec and implement** |
| Battery register 0x04 → 0x64 | Yes | Correct | Implement |
| `readBatteryMv() * 100` | Yes | Correct | Implement |
| `voltageToPercent()` table | Yes | Needs verification | Verify against device/docs |
| Concurrent register read race | No | Real bug | Consider mutex/queue |
| Register 0x50 for chip time | N/A | Undocumented | Verify with device |

---

*Review completed by Agent 1 (Wt901Parser Deep Reviewer)*
*Sources: WT901BLECL datasheet (WitMotion), `Wt901Parser.kt`, `BleManager.kt`, `BleRepositoryImpl.kt`, `Wt901ParserTest.kt`*
