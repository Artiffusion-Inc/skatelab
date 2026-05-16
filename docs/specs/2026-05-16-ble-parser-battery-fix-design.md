# BLE Parser & Battery Fix Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Fix 6 bugs in WT901 BLE parser and battery reading that cause register reads to timeout and battery percentage to show 0%.

**Architecture:** Fix Wt901Parser's 0x71 frame handling (frame size, checksum skip, register address, data offset) and BleRepositoryImpl's battery register and raw-to-percent conversion.

**TechStack:** Kotlin, Android BLE, JUnit 5

---

## Background

Device testing revealed:
- Battery percentage shows "Л:0% П:0%" for both sensors
- Logcat shows `readRegisterResponse: timeout for reg=0x68/0x60/0x4/0x64` during IMU streaming
- Reference app (WT901BLECL) successfully reads registers during streaming

Root cause: Wt901Parser treats 0x71 (register read response) frames as 11-byte individual frames, but BLE 0x71 frames are 20 bytes. This causes buffer desync — the parser reads 11 bytes, leaves 9 residual bytes, and subsequent frames can't be parsed. The 0x71 responses never reach `readRegisterResponse()`, causing timeouts.

Secondary bug: `readBattery()` reads register 0x04 (BAUD rate, not battery) and incorrectly interprets the result as a 0-100 percentage. The correct register is 0x64 (battery), which returns a raw integer. The WT901BLECL reference app uses raw values with thresholds 680-850 (DeviceControlActivity.java). The physical unit is unverified — likely centivolts for a 2S LiPo or raw ADC counts via voltage divider.

Additional bug: `isChecksumValid()` is called for 0x71 frames, but BLE 0x71 frames have no checksum. Byte 10 is data (`d3L`), not a checksum. This causes every 0x71 frame to fail validation → shift by 1 byte → desync → all 0x71 responses dropped. Without this fix, the frame size fix is ineffective.

## Bug 1: 0x71 Frame Size

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

## Bug 2: Checksum Validation for 0x71

**File:** `Wt901Parser.kt`

**Current (broken):** `isChecksumValid()` is called for all non-combined frames, including 0x71. It sums bytes 0..9 and checks against byte 10. In a 20-byte 0x71 frame, byte 10 is `d3L` (data), not a checksum. This virtually always fails, causing `shiftBuffer(1)` and desync.

**Evidence:** The WT901BLECL reference app (`Data.java`) has NO checksum validation. The WitMotion datasheet 20-byte BLE 0x71 format has no checksum byte.

**Fix:** Skip checksum validation for `TYPE_REG_READ`:
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

**Critical:** Without this fix, the frame size fix (Bug 1) is ineffective — 0x71 frames will still be dropped.

## Bug 3: Register Address Parsing

**Current:**
```kotlin
val register = buffer[2].toInt() and 0xFF
```

BLE 0x71 format: `[0x55][0x71][RegL][RegH][d0L][d0H]...[d7L][d7H]` = 20 bytes. `buffer[2]` = RegL.

**Verdict:** Register address parsing is correct. No change needed.

## Bug 4: Data Offset and Length

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

## Bug 5: Battery Register

**File:** `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt`

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
    val result = bleManager.readRegisterResponse(sensorId, 0x64)  // 0x64 = battery
    return result.map { data ->
        rawToPercent(data[0].toInt())  // Use reference-app thresholds
    }
}

/**
 * Convert raw battery register value to percentage.
 * Thresholds from WT901BLECL reference app (DeviceControlActivity.java).
 * Physical unit of register 0x64 is unverified — may be centivolts (2S LiPo)
 * or raw ADC counts via voltage divider.
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

**Note:** The original spec assumed register 0x64 returns "millivolts / 100" (384 = 3.84V). The WT901BLECL reference app uses raw values with thresholds 680-850 with NO multiplication. The unit is unverified — the reference app's thresholds are the only ground truth.

## Bug 6: readBatteryMv

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

**Fix:** Return raw value (unit unverified, do NOT multiply by 100):
```kotlin
override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt()  // Raw value — unit unverified. TODO: compare with multimeter.
    }
```

**Note:** The original spec assumed the register returns mV/100 and multiplied by 100. The reference app uses the raw value directly. Do NOT multiply until hardware verification confirms the unit.

## Testing

- Update `Wt901ParserTest` to test 0x71 frames as 20-byte BLE format
- Add test for 0x71 checksumless parsing (arbitrary byte 10 should not cause failure)
- Add test for `rawToPercent()`
- Verify existing `parseRegisterReadResponseDoesNotInterfereWithImuCycle` still passes with 20-byte 0x71
- Add test for 0x71 interleaved with 0x61 in a single notification buffer

## Files to Change

| File | Change |
|------|--------|
| `Wt901Parser.kt` | Add `REG_READ_FRAME_SIZE = 20`, fix frame size logic, **skip checksum for 0x71**, fix `parseRegisterReadFrame` data offset/length |
| `BleRepositoryImpl.kt` | Fix `readBattery` register 0x04→0x64, add `rawToPercent()` with reference-app thresholds, fix `readBatteryMv` (no *100) |
| `Wt901ParserTest.kt` | Update 0x71 test frames to 20-byte BLE format, add checksumless test, add interleaving test |
| `SensorInfo.kt` | No change needed (already has `batteryPercent` and `batteryMv`) |