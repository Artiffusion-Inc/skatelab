# BLE Feature Expansion — Battery, Device ID, Extended 0x71, Time Config

Date: 2026-05-14

## Context

WT901BLECL reference app (https://github.com/vrublack/WT901BLECL) reveals register addresses and commands our app doesn't use. Four features are valuable for figure skating biomechanics:

1. **Battery monitoring** — `readBattery` exists in `BleRepository` but only reads register 0x04 (%). Reference app also reads 0x64 (mV).
2. **Device ID** — register 0x68 identifies specific sensors.
3. **Extended 0x71 parsing** — register reads for 0x60 (firmware), 0x64 (battery mV), 0x68 (device ID).
4. **Time configuration** — commands 0x30/0x31/0x32 write Android time to sensor, improving sync accuracy.

## Scope

Full stack: BLE commands → domain → ViewModel → UI.

## Domain Models

### SensorInfo

```kotlin
// domain/model/SensorInfo.kt
data class SensorInfo(
    val deviceId: String,         // 0x68 → hex string
    val firmwareVersion: String,  // 0x60 → "major.minor"
    val batteryPercent: Int,       // 0x04 → 0-100
    val batteryMv: Int,           // 0x64 → millivolts
)
```

No new models for time config — it's automatic, exposed through existing `TimeSynchronizer`.

## Wt901Commander — New Commands

### Register reads (existing `readRegister(reg)` mechanism)

| Register | Data | Parse |
|----------|------|-------|
| 0x68 | Device ID | 3×int16 → hex string |
| 0x60 | Firmware version | 2 int16 → "major.minor" |
| 0x64 | Battery voltage (mV) | 1 int16 → millivolts |

### Time configuration writes

```
0xFF 0xAA 0x30 month (year-2000)    — Year/Month
0xFF 0xAA 0x31 hour   day           — Hour/Day
0xFF 0xAA 0x32 second minute        — Second/Minute
0xFF 0xAA 0x00 0x00 0x00           — Save (existing save())
```

New methods:

```kotlin
fun setTimeYearMonth(year: Int, month: Int): ByteArray
fun setTimeHourDay(hour: Int, day: Int): ByteArray
fun setTimeSecondMinute(second: Int, minute: Int): ByteArray
fun timeConfigSequence(): List<CommandStep>
```

`timeConfigSequence()` = unlock → setTimeYearMonth → setTimeHourDay → setTimeSecondMinute → save, with appropriate delays between each.

## BleRepository — New Methods

```kotlin
// Added to existing interface
suspend fun readDeviceId(sensorId: SensorId): Result<String>
suspend fun readFirmwareVersion(sensorId: SensorId): Result<String>
suspend fun readBatteryMv(sensorId: SensorId): Result<Int>
suspend fun configureSensorTime(sensorId: SensorId): Result<Unit>
fun readSensorInfo(sensorId: SensorId): Flow<SensorInfo?>
```

Implementation in `BleRepositoryImpl`:
- `readDeviceId` → `bleManager.readRegisterResponse(sensorId, 0x68)` → format 3 shorts as hex string
- `readFirmwareVersion` → `bleManager.readRegisterResponse(sensorId, 0x60)` → format as "major.minor"
- `readBatteryMv` → `bleManager.readRegisterResponse(sensorId, 0x64)` → first short as mV
- `configureSensorTime` → `bleManager.sendSequence(sensorId, Wt901Commander.timeConfigSequence())`
- `readSensorInfo` → combines all 4 register reads into `SensorInfo` flow

## UseCases

### ReadSensorInfoUseCase

```kotlin
class ReadSensorInfoUseCase @Inject constructor(
    private val bleRepository: BleRepository
) {
    suspend operator fun invoke(sensorId: SensorId): Result<SensorInfo>
}
```

Fetches deviceId (0x68), firmwareVersion (0x60), batteryPercent (0x04), batteryMv (0x64) in parallel via `async`. Returns combined `SensorInfo`.

### ConfigureSensorTimeUseCase

```kotlin
class ConfigureSensorTimeUseCase @Inject constructor(
    private val bleRepository: BleRepository
) {
    suspend operator fun invoke(sensorId: SensorId): Result<Unit>
}
```

Sends time config command sequence to sensor.

## Time Config — Automatic Trigger

Time config runs automatically inside `TimeSynchronizerImpl.sync()` (which wraps `PeriodicTimeSync`):

```
sync(scope):
  1. configureSensorTime(LEFT)  — only if offset > 1 second
  2. configureSensorTime(RIGHT) — only if offset > 1 second
  3. readChipTime(LEFT)   — existing offset calculation
  4. readChipTime(RIGHT)  — existing offset calculation
```

Condition: only write time to sensor when current offset exceeds 1 second. Avoids unnecessary writes when sensor clock is already close.

No manual UI trigger. No button. Fully automatic before streaming starts.

## ViewModel Changes

### BleScanViewModel

New state:

```kotlin
private val _sensorInfo = MutableStateFlow<Map<SensorId, SensorInfo?>>(emptyMap())
val sensorInfo: StateFlow<Map<SensorId, SensorInfo?>> = _sensorInfo
```

New actions:

```kotlin
fun refreshSensorInfo(sensorId: SensorId)  // launches ReadSensorInfoUseCase
```

Auto-refresh: when `connectionState` changes to CONNECTED for a sensor, automatically call `refreshSensorInfo`.

### RecordingViewModel

No changes. Time config is handled inside `TimeSynchronizer.sync()` before streaming starts.

## UI Changes

### BleScanScreen — ScanDeviceRow

When sensor is connected, show below the device name/address:

```
🪫 85% (3850mV)    ID: A3F2    FW: 1.2
```

Layout: single row of `Text` composables. Battery icon + percent + mV on left. Device ID + FW on right. Updated when `sensorInfo` flow emits.

Refresh: auto on connect. Pull-to-refresh not needed — data doesn't change fast.

## What We Don't Touch

- `ImuSample` — no magnetometer in 0x61 streaming frame
- `Wt901Parser` — 0x71 parsing already works (3×int16 is correct for all register reads)
- `ImuCollector` — no changes
- Recording flow — time config is transparent, handled by `TimeSynchronizer`
- ACC L/R calibration (0x01 0x05/0x06) — not needed per user decision
- Magnetometer calibration (0x01 0x07) — out of scope for this iteration

## Register Address Map (Consolidated)

| Register | Read/Write | Purpose | Data Format |
|----------|-----------|---------|-------------|
| 0x03 | W | Output rate | byte: 0x09=100Hz |
| 0x04 | R | Battery % | int16 → 0-100 |
| 0x50 | R | Chip time | 3×int16 → 48-bit ns |
| 0x60 | R | Firmware version | 2×int16 → major.minor |
| 0x64 | R | Battery voltage | int16 → millivolts |
| 0x68 | R | Device ID | 3×int16 → hex string |
| 0x30 | W | Time: year/month | byte=month, byte=(year-2000) |
| 0x31 | W | Time: hour/day | byte=hour, byte=day |
| 0x32 | W | Time: second/minute | byte=second, byte=minute |

## Testing

- `Wt901CommanderTest` — verify new time config command bytes and sequence
- `ReadSensorInfoUseCaseTest` — mock register reads, verify SensorInfo assembly
- `ConfigureSensorTimeUseCaseTest` — verify command sequence sent
- `BleScanViewModelTest` — verify auto-refresh on connect, sensorInfo state
- `TimeSynchronizerImplTest` — verify time config called when offset > 1s, skipped when offset < 1s
