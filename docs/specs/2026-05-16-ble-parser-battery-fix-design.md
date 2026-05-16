# BLE Parser & Battery Fix Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 bugs in WT901 BLE parser and battery reading that cause register reads to timeout and battery percentage to show 0%.

**Architecture:** Fix Wt901Parser's 0x71 frame handling (frame size, register address, data offset) and BleRepositoryImpl's battery register and voltage-to-percent conversion.

**TechStack:** Kotlin, Android BLE, JUnit 5

---

## Background

Device testing revealed:
- Battery percentage shows "Л:0% П:0%" for both sensors
- Logcat shows `readRegisterResponse: timeout for reg=0x68/0x60/0x4/0x64` during IMU streaming
- Reference app (WT901BLECL) successfully reads registers during streaming

Root cause: Wt901Parser treats 0x71 (register read response) frames as 11-byte individual frames, but BLE 0x71 frames are 20 bytes. This causes buffer desync — the parser reads 11 bytes, leaves 9 residual bytes, and subsequent frames can't be parsed. The 0x71 responses never reach `readRegisterResponse()`, causing timeouts.

Secondary bug: `readBattery()` reads register 0x04 (BAUD rate, not battery) and incorrectly interprets the result as a 0-100 percentage. The correct register is 0x64 (battery voltage), which returns millivolts/100 and needs a conversion table.

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

## Bug 2: Register Address Parsing

**Current (broken):**
```kotlin
val register = buffer[2].toInt() and 0xFF
```

**Fix:** BLE 0x71 format is `[0x55][0x71][RegL][RegH][data...]`. Register address is RegL at `buffer[2]`:
```kotlin
val register = buffer[2].toInt() and 0xFF  // This is actually correct — RegL is at offset 2
```

Wait — on second look, `buffer[2]` IS RegL. The register byte is correct. But verify offset against BLE 0x71 format: `[0x55][0x71][RegL][RegH][d0L][d0H]...[d7L][d7H]` = 20 bytes. So:
- `buffer[0]` = 0x55
- `buffer[1]` = 0x71
- `buffer[2]` = RegL ← this is what we want
- `buffer[3]` = RegH

**Verdict:** Register address parsing is correct. No change needed.

## Bug 3: Data Offset and Length

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

## Bug 4: Battery Register

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
    val result = bleManager.readRegisterResponse(sensorId, 0x64)  // 0x64 = battery voltage
    return result.map { data ->
        voltageToPercent(data[0].toInt())  // Convert mV/100 to percentage
    }
}

private fun voltageToPercent(mv100: Int): Int {
    val mv = mv100 * 100  // Register returns mV/100 (e.g., 384 = 3.84V)
    return when {
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
}
```

**Note:** Register 0x64 returns the raw voltage value. The official WitMotion BLE protocol documentation specifies: register value = millivolts / 100. So 384 = 3.84V = ~3840mV. The conversion table above uses millivolts.

## Bug 5: readBatteryMv

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

**Fix:** Return actual millivolts:
```kotlin
override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)
    return result.map { data ->
        data[0].toInt() * 100  // Convert mV/100 to mV
    }
}
```

## Testing

- Update `Wt901ParserTest` to test 0x71 frames as 20-byte BLE format
- Add test for `voltageToPercent()`
- Verify existing `parseRegisterReadResponseDoesNotInterfereWithImuCycle` still passes with 20-byte 0x71

## Files to Change

| File | Change |
|------|--------|
| `Wt901Parser.kt` | Add `REG_READ_FRAME_SIZE = 20`, fix frame size logic, fix `parseRegisterReadFrame` data offset/length |
| `BleRepositoryImpl.kt` | Fix `readBattery` register 0x04→0x64, add `voltageToPercent()`, fix `readBatteryMv` |
| `Wt901ParserTest.kt` | Update 0x71 test frames to 20-byte BLE format |
| `SensorInfo.kt` | No change needed (already has `batteryPercent` and `batteryMv`) |