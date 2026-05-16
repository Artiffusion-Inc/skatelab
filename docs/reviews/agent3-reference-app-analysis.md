# WT901BLECL Reference App Analysis

> Agent 3 report: ground-truth analysis of the WitMotion WT901BLECL reference app
> by vrublack (https://github.com/vrublack/WT901BLECL).
> Date: 2026-05-16

---

## 1. Executive Summary

The reference app (WT901BLECL) is a **working** Android app that communicates with WitMotion WT901 BLE sensors. It successfully reads registers during IMU streaming and displays battery levels. Our app has 5 critical bugs that diverge from the reference pattern. The root cause is a misunderstanding of the 0x71 frame format in BLE mode: the reference app receives **20-byte packets** for both 0x61 and 0x71 frames, while our parser treats 0x71 as an 11-byte individual frame with checksum.

### Top 5 Findings

1. **0x71 frame size is 20 bytes, not 11.** Both 0x61 and 0x71 arrive in 20-byte BLE notifications.
2. **0x71 data layout:** register at `buffer[2]`, 8 shorts of data at bytes 4-19 (no checksum).
3. **Battery register is 0x64, not 0x04.** Our `readBattery()` reads baud rate (0x04).
4. **Battery value is used raw, not multiplied by 100.** Reference thresholds: 680-850 (likely centivolts, 2S LiPo).
5. **Register reads happen simultaneously with streaming.** No pause, no queue, no mutex — just fire writes through Android's serialized GATT write path.

---

## 2. Reference App Architecture

### 2.1 Key Source Files

| File | Role |
|------|------|
| `BluetoothLeService.java` | BLE GATT service, connection management, frame dispatch |
| `DeviceControlActivity.java` | UI, periodic register read threads, battery icon updates |
| `Data.java` | Frame parser for 0x61 and 0x71 frames |
| `Constants.java` | Register read command definitions (0x27 prefix) |

### 2.2 BLE Characteristics

```java
private static final CharSequence CHARACTERISTIC_WRITE = "ffe9";
private static final CharSequence CHARACTERISTIC_READ = "ffe4";
private static final String CHARACTERISTIC_READ_DESCRIPTOR = "00002902-0000-1000-8000-00805f9b34fb";
```

- **FFE9** (write): All commands sent here (`setRate`, register reads, unlock, etc.)
- **FFE4** (notify): IMU data and register read responses arrive here
- **CCCD** (`00002902...`): Enabled with `ENABLE_NOTIFICATION_VALUE`

### 2.3 Connection Flow (Proven Pattern)

1. `connectGatt()` -> `onConnectionStateChange(STATE_CONNECTED)`
2. `discoverServices()` -> `onServicesDiscovered()`
3. Find FFE4 (notify) + FFE9 (write)
4. `setCharacteristicNotification(FFE4, true)` + write CCCD descriptor
5. **1-second delay** -> send `setRate(0x09)` via FFE9
6. Data streams automatically via FFE4 notifications

**No unlock, no save, no accCalibrate on connect.** Only `setRate(0x09)`.

---

## 3. Frame Parsing (0x61 and 0x71)

### 3.1 Frame Size

The reference app checks `packBuffer.length == 20` before parsing:

```java
private void handleBLEData(String device, byte[] packBuffer) {
    // ...
    if (packBuffer.length == 20) {
        formatted = mData.get(device).update(packBuffer);
        // ...
    }
}
```

**Critical implication:** Both 0x61 and 0x71 frames arrive as exactly 20-byte packets. The reference app IGNORES packets of any other size. If MTU > 20 and the sensor packs multiple frames into one notification, the reference app drops the entire packet.

### 3.2 0x61 Combined Frame Layout (20 bytes)

From `Data.java` lines 76-86:

```java
case 0x61:
    for (int i = 0; i < 9; i++) {
        fData[i] = (((short) packBuffer[i * 2 + 3]) << 8) | ((short) packBuffer[i * 2 + 2] & 0xff);
    }
    // ACC: fData[0..2] / 32768 * 16
    // GYRO: fData[3..5] / 32768 * 2000
    // ANGLE: fData[6..8] / 32768 * 180
```

| Byte Offset | Content |
|-------------|---------|
| 0 | 0x55 (header) |
| 1 | 0x61 (type) |
| 2-3 | AccX (int16 LE) |
| 4-5 | AccY (int16 LE) |
| 6-7 | AccZ (int16 LE) |
| 8-9 | GyrX (int16 LE) |
| 10-11 | GyrY (int16 LE) |
| 12-13 | GyrZ (int16 LE) |
| 14-15 | Roll (int16 LE) |
| 16-17 | Pitch (int16 LE) |
| 18-19 | Yaw (int16 LE) |

**No checksum.** Scale factors: ACC = 16/32768, GYRO = 2000/32768, ANGLE = 180/32768.

### 3.3 0x71 Register Read Response Layout (20 bytes)

From `Data.java` lines 88-115:

```java
case 0x71:
    if (fData[2] != 0x68) {  // BUG: always true (fData[2] is 0 for new array)
        for (int i = 0; i < 8; i++) {
            fData[i] = (((short) packBuffer[i * 2 + 5]) << 8) | ((short) packBuffer[i * 2 + 4] & 0xff);
        }
    }
    switch (packBuffer[2]) {  // register address
        case 0x3A: // magnetometer
            System.arraycopy(fData, 0, magn, 0, 3);
        case 0x45: // pressure
            pressure = ((((long) packBuffer[7]) << 24) ... packBuffer[4]);
            altitude = ((((long) packBuffer[11]) << 24) ... packBuffer[8]) / 100.0f;
        case 0x41: // port
            for (int i = 0; i < 4; i++) port[i] = (float) (fData[i]);
        case 0x51: // quaternion
            for (int i = 0; i < 4; i++) quaternion[i] = (float) (fData[i] / 32768.0);
        case 0x40: // temperature
            temperature = (float) (fData[0] / 100.0);
        case 0x64: // battery
            battery = fData[0];
    }
```

| Byte Offset | Content |
|-------------|---------|
| 0 | 0x55 (header) |
| 1 | 0x71 (type) |
| 2 | Register address (e.g. 0x64 for battery) |
| 3 | Unknown / padding (not used by reference) |
| 4-5 | Data[0] (int16 LE) |
| 6-7 | Data[1] (int16 LE) |
| 8-9 | Data[2] (int16 LE) |
| 10-11 | Data[3] (int16 LE) |
| 12-13 | Data[4] (int16 LE) |
| 14-15 | Data[5] (int16 LE) |
| 16-17 | Data[6] (int16 LE) |
| 18-19 | Data[7] (int16 LE) |

**No checksum in BLE mode.** The 8 shorts (16 bytes) at bytes 4-19 are the register read response data. Different registers use different subsets of these 8 shorts.

### 3.4 Key Observations about 0x71 Parsing

1. **Bug in reference app:** `if (fData[2] != 0x68)` is always true because `fData` is a newly allocated float array (all zeros). The intended check was probably `packBuffer[2] != 0x68`, but due to this bug, the 8-short read always executes.
2. **Register 0x68 (Device ID)** has no handler in the switch statement — responses are parsed but ignored.
3. **Register 0x45 (pressure)** reads directly from `packBuffer[4..11]` as two 32-bit big-endian values, not from `fData`.
4. **All other registers** read from `fData[0..N]` which was populated from bytes 4-19.

---

## 4. Battery Reading Approach

### 4.1 Register

```java
public static byte[] cell = new byte[]{(byte) 0xff, (byte) 0xaa, 0x27, 0x64, 0x00};
```

**Register 0x64** is read for battery. The command prefix is `FF AA 27 64 00`.

### 4.2 When Battery is Read

1. **Immediately on connect:** `writeByes(device, cell)` in `onConnectionStateChange(STATE_CONNECTED)`
2. **Every 5 seconds:** via `Handler` in `DeviceControlActivity` (lines 485-496)
3. **Battery value arrives via 0x71 frame** interleaved with 0x61 streaming frames

### 4.3 Voltage-to-Percentage Conversion

The reference app does NOT convert voltage to a 0-100 percentage. It uses the **raw register value directly** and maps it to 5 icon levels:

```java
if (data.getBattery() < 680) { /* cell1 */ }
if (data.getBattery() >= 680 && data.getBattery() < 735) { /* cell2 */ }
if (data.getBattery() >= 745 && data.getBattery() < 775) { /* cell3 */ }
if (data.getBattery() >= 775 && data.getBattery() < 850) { /* cell4 */ }
if (data.getBattery() >= 850) { /* cell5 */ }
```

**Critical observations:**
- No multiplication by 100. The raw value IS the voltage in some unit.
- Thresholds: 680, 735, 745, 775, 850.
- **Gap:** 735-744 has no condition (reference app bug).
- These values are consistent with a **2S LiPo battery** (7.4V nominal, 8.4V max) measured in **centivolts** (0.01V):
  - 680 = 6.80V (empty)
  - 850 = 8.50V (full)
- Our spec assumes single-cell Li-ion (3.7V nominal) with millivolt thresholds (3960mV = 100%). This is a **fundamental discrepancy** that must be resolved with hardware testing.

### 4.4 Data Type

In `Data.java`:
```java
case 0x64:
    battery = fData[0];  // fData[0] is a float, raw int16 from bytes 4-5
```

`battery` is a `float` storing the raw signed int16 value from the register response.

---

## 5. Streaming + Register Read Coexistence

### 5.1 No Pause, No Queue

The reference app does **NOT** pause IMU streaming to read registers. It sends register read commands (`FF AA 27 XX 00`) continuously while 0x61 frames stream in via notifications.

### 5.2 Two Concurrent Sources of Register Reads

**Source 1: UI refresh thread** (DeviceControlActivity, lines 825-856)
```java
mRefreshSensor = new Thread(new Runnable() {
    @Override
    public void run() {
        while (true) {
            if (mService != null && mService.isAnyConnected()) {
                switch (DisplayIndex) {
                    case 2:  mService.writeByes(mCurrentDevice, REQUEST_ANGLE);  break;  // 0x40
                    case 3:  mService.writeByes(mCurrentDevice, REQUEST_MAGN);   break;  // 0x3A
                    case 4:  mService.writeByes(mCurrentDevice, REQUEST_PRESSURE); break; // 0x45
                    case 5:  mService.writeByes(mCurrentDevice, REQUEST_PORT);     break;  // 0x41
                    case 6:  mService.writeByes(mCurrentDevice, REQUEST_QUATER); break;  // 0x51
                }
            }
            Thread.sleep(240);
        }
    }
});
```

**Source 2: Periodic battery + device ID poll** (every 5 seconds)
```java
Handler handler = new Handler() {
    @Override
    public void handleMessage(Message msg) {
        if (msg.what == 0) {
            mService.writeByes(mCurrentDevice, BluetoothLeService.mDeviceID);  // 0x68
            mService.writeByes(mCurrentDevice, BluetoothLeService.cell);       // 0x64
        }
    }
};
```

### 5.3 How Responses Are Distinguished

The 0x71 response contains the register address at `packBuffer[2]`. The parser switches on this byte to route data to the correct field. Both 0x61 and 0x71 frames arrive on the same FFE4 notification characteristic. The parser distinguishes them by the type byte (`packBuffer[1]`):
- `0x61` -> IMU data
- `0x71` -> register read response

### 5.4 No Explicit Write Queue

The reference app calls `gatt.writeCharacteristic()` directly from multiple threads (UI thread, background threads). Android BLE internally serializes writes per connection. There is no application-level queue or mutex.

---

## 6. Comparison with Our Implementation

### 6.1 Frame Parser: Wt901Parser.kt

| Aspect | Reference App (Data.java) | Our App (Wt901Parser.kt) | Verdict |
|--------|---------------------------|--------------------------|---------|
| **0x71 frame size** | 20 bytes | 11 bytes (uses `INDIVIDUAL_FRAME_SIZE`) | **CRITICAL BUG** |
| **0x71 checksum** | None | Validated with `isChecksumValid()` | **WRONG** |
| **0x71 register offset** | `buffer[2]` | `buffer[2]` | Correct |
| **0x71 data offset** | Bytes 4-19 (8 shorts) | Bytes 3-8 (3 shorts) | **CRITICAL BUG** |
| **0x61 frame size** | 20 bytes | 20 bytes (`COMBINED_FRAME_SIZE`) | Correct |
| **Buffering** | None (drops non-20-byte packets) | 512-byte ring buffer with framing | Our approach is more robust |
| **Plausibility check** | None for 0x61 | `isCombinedFramePlausible()` | Our addition, useful |

### 6.2 Battery Reading: BleRepositoryImpl.kt

| Aspect | Reference App | Our App | Verdict |
|--------|---------------|---------|---------|
| **Register** | 0x64 | 0x04 (baud rate!) | **CRITICAL BUG** |
| **Value handling** | Raw `fData[0]` (no scaling) | `data[0].toInt().coerceIn(0,100)` | **WRONG** |
| **Voltage unit** | Centivolts (680 = 6.80V) | Millivolts/100 (384 = 3840mV) | **DISCREPANCY** |
| **Battery thresholds** | 680, 735, 745, 775, 850 | 3960, 3930, 3870, 3820... | **DISCREPANCY** |
| **readBatteryMv** | Reads 0x64, returns raw value | Reads 0x64, returns `data[0] * 100` | Partially correct |

### 6.3 Streaming + Register Reads: BleManager.kt

| Aspect | Reference App | Our App | Verdict |
|--------|---------------|---------|---------|
| **Write serialization** | Android BLE internal queue | `HandlerThread` (workHandler) | Our approach is better |
| **Read during streaming** | Yes, continuously | `readRegisterResponse()` suspends for one response | Different model, both valid |
| **Queue depth** | Unbounded (fire-and-forget) | `MutableSharedFlow` with buffer 8 for results | Our model has backpressure |
| **Frame interleaving** | Handled by type byte switch | Same (0x61 vs 0x71) | Same approach |
| **MTU handling** | Drops packets != 20 bytes | Supports multi-frame notifications | Our approach is more robust |

---

## 7. Root Cause Analysis

### Why Our Register Reads Timeout

1. We send `readRegister(0x64)` via `writeBytes()`
2. Sensor responds with a 20-byte 0x71 frame
3. Our `Wt901Parser.feed()` sees `0x71` at `buffer[1]`
4. It sets `frameSize = INDIVIDUAL_FRAME_SIZE (11)` because 0x71 is not `TYPE_COMBINED`
5. It reads 11 bytes, validates checksum (byte 10) — **which fails** because there's no checksum in BLE 0x71
6. It shifts 1 byte and tries again, now desynced
7. The remaining 9 bytes of the 0x71 frame + subsequent bytes create garbage
8. The `onRegisterRead` callback never fires
9. `readRegisterResponse()` times out waiting for the callback

### Why Our Battery Shows 0%

1. `readBattery()` reads register **0x04** (baud rate), not 0x64
2. Even if it read 0x64, `coerceIn(0, 100)` would clamp a raw value of 680 to 100, not map it correctly
3. The percentage conversion formula is completely wrong for the actual register value range

---

## 8. Specific Recommendations

### 8.1 Fix Wt901Parser.kt (0x71 Frame Handling)

```kotlin
// Add to companion object
private const val REG_READ_FRAME_SIZE = 20

// Fix frame size logic
val frameSize = when (frameType) {
    TYPE_COMBINED -> COMBINED_FRAME_SIZE
    TYPE_REG_READ -> REG_READ_FRAME_SIZE
    else -> INDIVIDUAL_FRAME_SIZE
}

// Fix parseRegisterReadFrame()
private fun parseRegisterReadFrame() {
    val reg = buffer[2].toInt() and 0xFF
    // BLE 0x71: 8 shorts at bytes 4-19, no checksum
    val data = ShortArray(8) { i -> readInt16LEShort(4 + i * 2) }
    onRegisterRead?.invoke(RegisterReadResult(reg, data))
}
```

**Do NOT validate checksum for 0x71 in BLE mode.** The 20-byte BLE packet has no checksum byte.

### 8.2 Fix BleRepositoryImpl.kt (Battery Register and Conversion)

```kotlin
override suspend fun readBattery(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)  // FIX: was 0x04
    return result.map { data ->
        voltageToPercent(data[0].toInt())
    }
}

// CRITICAL: thresholds must match actual hardware battery
// Reference app uses raw values 680-850 (likely 2S LiPo, centivolts)
// Our spec used single-cell Li-ion thresholds — verify with hardware test
private fun voltageToPercent(raw: Int): Int = when {
    raw >= 850 -> 100
    raw >= 775 -> 80
    raw >= 745 -> 60
    raw >= 735 -> 40
    raw >= 680 -> 20
    else -> 0
}

override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt()  // Raw value — do NOT multiply by 100 until hardware test confirms unit
    }
```

### 8.3 Verify Battery Voltage Unit with Hardware

The reference app's thresholds (680-850) strongly suggest a **2S LiPo battery** measured in centivolts. Our spec assumed a single-cell Li-ion with millivolts/100.

**Action:** Connect a WT901BLECL sensor, read register 0x64, and measure actual battery voltage with a multimeter. Compare raw register value to measured voltage to determine the exact scale factor.

If raw value / measured_voltage = 100, unit is centivolts.
If raw value / measured_voltage = 1, unit is volts.
If raw value / measured_voltage = 1000, unit is millivolts.

### 8.4 Keep Our Buffering Approach

Our 512-byte ring buffer with multi-frame parsing is **superior** to the reference app's "drop non-20-byte packets" approach. Do not regress to the reference app's simplistic length check. Just fix the 0x71 frame size.

### 8.5 Keep Our Write Serialization

Our `HandlerThread` for GATT writes is **superior** to the reference app's unsynchronized multi-thread writes. Keep it.

### 8.6 Register Read Model

The reference app uses fire-and-forget register reads with no response tracking. Our `readRegisterResponse()` suspend function with `MutableSharedFlow` result matching is a **better abstraction** for Kotlin coroutines. Keep the model, just fix the parser so responses actually arrive.

### 8.7 Handle 0x68 Device ID in 0x71

The reference app parses 0x71 responses for register 0x68 but has no case for it in the switch (falls through, returns null). Our `readDeviceId()` in `BleRepositoryImpl` expects 3 shorts from `data[0..2]`. With the 20-byte 0x71 fix, `data` will contain 8 shorts. `data[0..2]` will still be the first 3 shorts at bytes 4-9. This should work.

However, verify that register 0x68 actually returns 3 useful shorts in bytes 4-9. The reference app's `fData[2] != 0x68` guard (buggy, always true) suggests the original developer thought 0x68 had a different format.

---

## 9. Testing Recommendations

1. **Unit test:** Create a 20-byte 0x71 frame with register 0x64 and data at bytes 4-5. Verify parser extracts `RegisterReadResult(0x64, data)` where `data[0]` is correct.
2. **Unit test:** Feed a sequence of 0x61 + 0x71 + 0x61 frames in a single buffer. Verify all three are parsed correctly without desync.
3. **Integration test:** Connect to real sensor, send `readRegister(0x64)`, verify response arrives within 500ms (not timeout).
4. **Hardware test:** Read 0x64 during active streaming. Compare raw value to multimeter reading.
5. **Regression test:** Ensure 0x51/0x52/0x59 individual frames still parse correctly (unchanged path).

---

## 10. Appendix: Full Reference App Command Log

### Commands Sent on Connect

```
FF AA 27 64 00   // read battery (0x64)
FF AA 27 68 00   // read device ID (0x68)
FF AA 03 09 00   // setRate(0x09) — after 1s delay
```

### Periodic Commands (During Streaming)

```
// Every 240ms (UI refresh thread, data-type dependent):
FF AA 27 40 00   // read angle (0x40)
FF AA 27 3A 00   // read magnetometer (0x3A)
FF AA 27 45 00   // read pressure (0x45)
FF AA 27 41 00   // read port (0x41)
FF AA 27 51 00   // read quaternion (0x51)

// Every 5 seconds (handler):
FF AA 27 68 00   // read device ID (0x68)
FF AA 27 64 00   // read battery (0x64)
```

### Other Commands (User-triggered)

```
FF AA 01 01 00   // accCalibrate
FF AA 01 00 00   // stopCalibration
FF AA 00 01 00   // factoryReset
FF AA 00 00 00   // save
FF AA 69 88 B5   // unlock
```

---

*Report generated by Agent 3 (Reference App Analyst). Ground truth source: /tmp/WT901BLECL (cloned from https://github.com/vrublack/WT901BLECL).*
