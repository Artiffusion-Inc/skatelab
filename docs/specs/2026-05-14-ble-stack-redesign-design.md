# BLE Stack Redesign — Based on WT901BLECL Reference

> Root cause: `accCalibrate()` in BLE connect sequence corrupted ACC offset on E8:17 sensor.
> Reference app (WT901BLECL by vrublack) proves sensor is fine — it sends only `setRate()` on connect.
> This redesign aligns our BLE stack with the proven reference pattern.

## Requirements

- 2 WT901 sensors simultaneously
- ACC in m/s², GYRO in °/s, quaternion from Euler→quat conversion (0x61 frame)
- ImuSample interface unchanged
- No camera/export/sync changes
- Must NOT send accCalibrate/unlock/save on connect (proven to corrupt ACC offset)

## Reference Pattern (WT901BLECL)

Connect flow:
1. `connectGatt()` → `onConnectionStateChange(CONNECTED)`
2. `discoverServices()` → find FFE4 (notify) + FFE9 (write)
3. `setCharacteristicNotification(FFE4, true)` + `writeDescriptor(CCCD ENABLE)`
4. 1s delay → `setRate(0x09)` — **only command sent on connect**
5. Data streams via CCCD notifications → `onCharacteristicChanged()`
6. If `packBuffer.length == 20` → parse as 0x61 frame

That's it. No unlock, no save, no accCalibrate, no OutputContent (RSW).

## Architecture After Redesign

### Files

```
data/ble/
├── Wt901Parser.kt          ← keep as-is (correct parsing, sign-extend fixed)
├── Wt901Commander.kt        ← simplify: remove UART sequences, keep only atomic commands
├── BleManager.kt            ← rewrite: simple GATT callback per WT901BLECL pattern
├── BleRepositoryImpl.kt    ← simplify: remove streamingMutexes, remove complex sequences
└── BleHandlerThread.kt     ← DELETE (logic moves into BleManager)
```

### Wt901Commander — Simplified

Keep only atomic commands:
- `setRate(rate: Int)` — **only command used on connect**
- `unlock()`, `save()`, `stopCalibration()`, `accCalibrate()` — recovery only
- `factoryReset()`, `restart()` — recovery only
- `readRegister(reg: Int)` — for 0x71 queries (battery, etc.)
- `wakeUp()` — for stubborn firmware

Remove:
- `configureSequence()` — UART-only, sends RSW (forbidden in BLE)
- `configureSequenceNoAccCal()` — UART-only, same issue
- `factoryResetSequence()` — caused GATT drop, not needed
- `bleConfigureSequence()` — replaced by single `setRate()`
- `bleFactoryResetSequence()` — same issue
- `startStreamingSequence()` / `stopStreamingSequence()` — no-op in BLE, 0x61 streams automatically

Keep as recovery helpers:
- `bleAccCalibrateSequence()` — manual ACC recovery button
- `bleAccCalibrateWithWakeSequence()` — for stubborn firmware

### BleManager — Rewrite

Based on WT901BLECL `BluetoothLeService`:

```kotlin
class BleManager(context: Context) {
    // Per-device state (like reference's HashMap<String, *>)
    private val gatts = ConcurrentHashMap<String, BluetoothGatt>()
    private val parsers = ConcurrentHashMap<String, Wt901Parser>()
    private val writeChars = ConcurrentHashMap<String, BluetoothGattCharacteristic>()

    // Single HandlerThread for all GATT writes (like reference)
    private val writeHandler = HandlerThread("BLE-Write").apply { start() }
    private val writeHandlerObj = Handler(writeHandler.looper)

    // Callback per device
    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt, status, newState) {
            when (newState) {
                STATE_CONNECTED -> {
                    gatt.discoverServices()
                }
                STATE_DISCONNECTED -> {
                    // cleanup, notify UI
                }
            }
        }

        override fun onServicesDiscovered(gatt, status) {
            if (status == GATT_SUCCESS) {
                setupDevice(gatt)  // find FFE4/FFE9, enable CCCD, schedule setRate
            }
        }

        override fun onCharacteristicChanged(gatt, characteristic) {
            val data = characteristic.value
            val address = gatt.device.address
            val parser = parsers[address] ?: return
            val sample = parser.feed(data, SystemClock.elapsedRealtimeNanos())
            sample?.let { onSample?.invoke(address, it) }
        }
    }

    private fun setupDevice(gatt: BluetoothGatt) {
        // Find FFE4 (notify) and FFE9 (write) characteristics
        // Enable CCCD on FFE4
        // Schedule setRate(0x09) after 1s delay
        // Like WT901BLECL getWorkableGattServices()
    }

    fun writeBytes(address: String, bytes: ByteArray) {
        // Route through writeHandler — single thread for all writes
        // Like reference writeByes()
    }
}
```

Key differences from current code:
- **No unlock/save on connect** — only setRate
- **No Mutex** — writeHandler serializes all writes (like reference)
- **No streamingMutexes** — CCCD handles start/stop, no markRecording/markStopped
- **No BleHandlerThread** — merged into BleManager
- **No explicitlyDisconnected** — simpler disconnect flow

### BleRepositoryImpl — Simplified

```kotlin
class BleRepositoryImpl(private val bleManager: BleManager) : BleRepository {
    // connect → bleManager.connect(address)
    // disconnect → bleManager.disconnect(address)
    // accCalibrateSensor → bleManager.writeBytes(sequence) — recovery only
    // factoryResetSensor → bleManager.writeBytes(factoryReset) — recovery only
}
```

Remove:
- `streamingMutexes` — not needed, CCCD handles streaming
- `markRecording/markStopped` — streaming is implicit
- `bleConfigure()` call from connect — replaced by simple setRate in BleManager.setupDevice()

### ConnectSensorUseCase — Simplified

```kotlin
class ConnectSensorUseCase(private val bleRepo: BleRepository) {
    suspend operator fun invoke(address: String): Result<SensorId> {
        bleRepo.connect(address)
        // That's it. No configuration sequence.
        // BleManager.setupDevice() sends setRate automatically.
    }
}
```

Remove:
- `bleConfigure()` / `configureSequenceNoAccCal()` call
- All references to Wt901Commander sequences from connect flow

## What Stays Unchanged

- `Wt901Parser` — correct parsing, sign-extend fixed
- `ImuSample` domain model — m/s² for ACC, °/s for GYRO
- `CalibrateSensorUseCase` — warm-up filter, gyro threshold
- `StartRecordingUseCase` / `StopRecordingUseCase` — recording lifecycle
- `ExportSessionUseCase` — zip export
- `ImuCollector` — sample collection
- `TimeSyncManager` / `PeriodicTimeSync` — time synchronization
- Camera layer — Camera2Recorder, CameraRepositoryImpl
- All presentation layer — ViewModels, Screens
- DI modules — only wiring changes for new BleManager constructor

## Safety Guarantees

1. **accCalibrate() NEVER sent on connect** — proven to corrupt ACC offset on some firmware
2. **RSW (OutputContent 0x02) NEVER written** — UART-only register, no-op or harmful in BLE
3. **unlock/save NEVER sent on connect** — unnecessary, WT901 streams 0x61 automatically
4. **factoryReset NEVER sent automatically** — causes GATT drop + reboot, recovery-only
5. **Only setRate(0x09) sent on connect** — same as reference, proven working

## Recovery Mechanisms (Manual Only)

If ACC offset corrupted (all zeros in 0x61 frame):
1. Factory reset button in BleScanScreen → `factoryReset()` → sensor reboots → reconnect → setRate
2. ACC calibrate button → `bleAccCalibrateSequence()` → stopCalib → unlock → stopCalib → unlock → accCalibrate → save
3. Wake-up + calibrate → `bleAccCalibrateWithWakeSequence()` for stubborn firmware

## Testing

- Existing Wt901Parser tests: unchanged, still pass
- Wt901Commander tests: update — remove sequence tests, add setRate/recovery tests
- BleManager tests: new — connect flow (setRate only), write queue, CCCD enable
- BleRepositoryImpl tests: simplify — no streamingMutex tests
- Integration: verify ACC data is non-zero after connect on E8:17 sensor
