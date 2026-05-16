# BLE Stack Redesign — Implementation Plan

> Spec: `docs/specs/2026-05-14-ble-stack-redesign-design.md`
> Reference: WT901BLECL `BluetoothLeService.java` by vrublack

## Order: bottom-up (leaf → consumer)

Changes propagate from low-level (command builder) to high-level (use cases, UI).
Each step compiles and tests before the next.

---

## Step 1: Simplify Wt901Commander

**File:** `data/ble/Wt901Commander.kt`

Remove:
- `configureSequence()` — UART-only, sends RSW
- `configureSequenceNoAccCal()` — UART-only, sends RSW
- `factoryResetSequence()` — UART-only, caused GATT drop
- `bleConfigureSequence()` — replaced by single `setRate()` in BleManager
- `bleFactoryResetSequence()` — recovery via atomic `factoryReset()` only
- `startStreamingSequence()` — no-op in BLE
- `stopStreamingSequence()` — no-op in BLE
- `setOutputContent()` — UART-only RSW register
- `REG_OUTPUT_CONTENT` constant

Add:
- `setRate(rate: Int): ByteArray` — atomic command (was `setOutputRate`, rename to match spec/reference)
- Rename `setOutputRate` → `setRate` for clarity

Keep:
- `unlock()`, `save()`, `stopCalibration()`, `accCalibrate()` — atomic commands
- `factoryReset()`, `restart()` — atomic commands
- `readRegister(reg: Int)` — register queries
- `wakeUp()` — stubborn firmware
- `bleAccCalibrateSequence()` — recovery helper
- `bleAccCalibrateWithWakeSequence()` — recovery helper
- All delay constants
- `CommandStep` data class

**Verify:** `./gradlew :app:test --tests "*.Wt901Commander*"` (update tests to match)

---

## Step 2: Rewrite BleManager

**File:** `data/ble/BleManager.kt` (complete rewrite, ~250 lines)

**Delete:** `data/ble/BleHandlerThread.kt` (logic merged into BleManager)

Architecture based on WT901BLECL `BluetoothLeService`:

```kotlin
class BleManager(context: Context, logger: AppLogger?) {
    // UUIDs (keep existing)
    // Per-device state via ConcurrentHashMap (like reference's HashMaps)
    val gatts, parsers, writeChars, notifyChars

    // Single HandlerThread for GATT writes + parsing (like reference)
    private val workThread = HandlerThread("BLE-Work").apply { start() }
    private val workHandler = Handler(workThread.looper)

    // Flows (keep existing API)
    scanResults, connectionState, imuSamples, registerReadResults, reconnectEvents

    // No: recordingSensors, explicitlyDisconnected, sensorMutexes, writeQueues, writeInProgress
    // No: per-sensor BleHandlerThread instances
}
```

### Connect flow (WT901BLECL pattern):

```
connect(sensorId, address)
  → addressToSensorId[address] = sensorId
  → createGattCallback(sensorId, address)  // single shared callback factory
  → device.connectGatt(context, false, callback)
  → wait CONNECTED or timeout 10s

onConnectionStateChange(CONNECTED)
  → gatts[address] = gatt
  → gatt.discoverServices()

onServicesDiscovered(GATT_SUCCESS)
  → find FFE4 (notify) + FFE9 (write)
  → writeChars[address] = writeChar (WRITE_TYPE_NO_RESPONSE)
  → setCharacteristicNotification(FFE4, true)
  → writeDescriptor(CCCD ENABLE)

onDescriptorWrite(CCCD, GATT_SUCCESS)
  → schedule setRate(0x09) after 1s delay on workHandler  ← ONLY command on connect
  → updateConnectionState(CONNECTED)
```

### Data flow:

```
onCharacteristicChanged(FFE4)
  → val bytes = characteristic.value.copyOf()
  → val arrivalNs = SystemClock.elapsedRealtimeNanos()
  → workHandler.post {
      val parser = parsers.getOrPut(address) { Wt901Parser() }
      val sample = parser.feed(bytes, arrivalNs)
      sample?.let { _imuSamples.tryEmit(sensorId to it) }
    }
```

### Write flow:

```
writeBytes(address, bytes)  // replaces sendCommand + sendSequence
  → workHandler.post {
      val char = writeChars[address] ?: return@post
      val gatt = gatts[address] ?: return@post
      char.value = bytes
      gatt.writeCharacteristic(char)
    }
```

### Disconnect flow:

```
disconnect(sensorId, address)
  → gatts.remove(address)?.disconnect()?.close()
  → parsers.remove(address)
  → writeChars.remove(address)
  → notifyChars.remove(address)
  → addressToSensorId.remove(address)
  → updateConnectionState(DISCONNECTED)
```

### Auto-reconnect (during recording):

```
onConnectionStateChange(DISCONNECTED)
  → close old GATT
  → if sensorId in recordingSensors:
      → updateConnectionState(RECONNECTING)
      → _reconnectEvents.tryEmit(sensorId)
      → workHandler.postDelayed(2000ms) { reconnect }
  → else:
      → updateConnectionState(DISCONNECTED)
```

### Keep from current code:
- UUID constants (FFE5, FFE4, FFE9, CCCD)
- Scan logic (startScan/stopScan) — unchanged
- `reRequestHighPriority()` — every 30s
- `readRegisterResponse()` — but simplified (no Mutex, use writeBytes)
- `ScanResult`, `ConnectionState` inner types
- All flow declarations (scanResults, connectionState, imuSamples, etc.)

### Remove from current code:
- `BleHandlerThread` per-sensor instances → single `workThread` in BleManager
- `sensorMutexes` → workHandler serializes all writes
- `writeQueues` / `writeInProgress` / `GattWriteEntry` → simple workHandler.post
- `explicitlyDisconnected` → simpler reconnect guard via `recordingSensors`
- `sendSequence()` → replaced by `writeBytes()` per step (caller handles delays)
- `sendCommand()` → replaced by `writeBytes()`
- `drainWriteQueue()` → not needed, workHandler is serial
- `completeSetup()` → inlined in onDescriptorWrite
- MTU negotiation → remove (reference doesn't use it, causes delays)

### New public API:

```kotlin
fun connect(sensorId: SensorId, address: String): Result<Unit>  // suspend
fun disconnect(sensorId: SensorId, address: String)
fun writeBytes(address: String, bytes: ByteArray)
fun writeSequence(address: String, steps: List<CommandStep>)  // suspend, delays between steps
fun readRegisterResponse(sensorId: SensorId, register: Int, timeoutMs: Long): Result<ShortArray>
fun markRecording(sensorId: SensorId)
fun markStopped(sensorId: SensorId)
```

**Verify:** Build compiles. No existing unit tests for BleManager (integration only).

---

## Step 3: Simplify BleRepositoryImpl

**File:** `data/ble/BleRepositoryImpl.kt`

Remove:
- `streamingMutexes` — not needed
- `bleConfigure()` method — BleManager sends setRate automatically
- `configureSensor()` — UART-only, dead code
- `configureSensorNoAccCal()` — UART-only, dead code
- `startStreaming()` / `stopStreaming()` — no-ops in BLE, 0x61 streams automatically

Simplify:
- `connect()` → just `bleManager.connect()`, no `bleConfigure()` after
- `accCalibrateSensor()` → `bleManager.writeSequence()`
- `factoryResetSensor()` → `bleManager.writeBytes(factoryReset)`
- `startStreaming()` → no-op (return success, 0x61 streams automatically)
- `stopStreaming()` → no-op (return success)

**Verify:** Build compiles.

---

## Step 4: Update BleRepository interface

**File:** `domain/repository/BleRepository.kt`

Remove:
- `bleConfigure(sensorId)` — no longer needed
- `configureSensor(sensorId)` — UART-only, dead code
- `configureSensorNoAccCal(sensorId)` — UART-only, dead code

Keep:
- `connect`, `disconnect`, `startStreaming`, `stopStreaming` (now no-ops for streaming but keep API for future)
- `factoryResetSensor`, `accCalibrateSensor` — recovery only
- `readBattery`, `readChipTime`
- `scanResults`, `connectionState`, `imuSamples`, `reconnectEvents`

**Verify:** Build compiles.

---

## Step 5: Simplify ConnectSensorUseCase

**File:** `domain/usecase/ConnectSensorUseCase.kt`

Before:
```kotlin
suspend fun invoke(sensorId, address): Result<Unit> {
    bleRepository.connect(sensorId, address).getOrElse { return Result.failure(it) }
    return bleRepository.bleConfigure(sensorId)  // ← REMOVE THIS
}
```

After:
```kotlin
suspend fun invoke(sensorId, address): Result<Unit> {
    return bleRepository.connect(sensorId, address)
    // BleManager.setupDevice() sends setRate(0x09) automatically
}
```

**Verify:** Build compiles.

---

## Step 6: Update ViewModel + UI

**File:** `presentation/ble/BleScanViewModel.kt`

- Remove `bleConfigure` references (none currently — it's in ConnectSensorUseCase)
- Verify `factoryResetSensor` and `accCalibrateSensor` still work via updated BleRepository
- No UI changes needed

**File:** `presentation/ble/BleScanScreen.kt`

- No changes needed (uses ViewModel API which is unchanged)

---

## Step 7: Delete BleHandlerThread

**File:** `data/ble/BleHandlerThread.kt` — DELETE

Logic merged into BleManager (single workThread for writes + parsing).

Remove all imports/references in BleManager (already rewritten in Step 2).

**Verify:** No other files import BleHandlerThread. Build compiles.

---

## Step 8: Update DI wiring

**File:** `di/AppModule.kt`

- BleManager is now created inside BleRepositoryImpl (like current code: `private val bleManager = BleManager(context, appLogger)`)
- No changes needed to AppModule unless constructor changes

**Verify:** Build compiles, `./gradlew :app:assembleDebug` succeeds.

---

## Step 9: Test on hardware via ADB

1. `./gradlew :app:assembleDebug`
2. `adb install -r app/build/outputs/apk/debug/app-debug.apk`
3. Open app → BleScanScreen
4. Connect LEFT sensor (E8:17 — the "broken" one)
5. Verify: ACC data non-zero (accMag ≈ 9.8 m/s² at rest)
6. Connect RIGHT sensor
7. Verify: ACC data non-zero on both sensors
8. Swap: LEFT ↔ RIGHT addresses
9. Verify: both still show non-zero ACC
10. Test ACC calibration recovery button (should still work)
11. Test factory reset recovery button (should still work)
12. Test recording flow: calibrate → start recording → stop → export

**Success criteria:**
- Both sensors show non-zero ACC on connect (no unlock/save corruption)
- Swapping LEFT/RIGHT doesn't break anything
- Recording + export works as before
