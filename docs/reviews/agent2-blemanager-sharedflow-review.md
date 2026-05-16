# Agent 2: BleManager & SharedFlow Review

> Date: 2026-05-16
> Scope: WT901 BLE register read/write flow, SharedFlow concurrency, 0x71/0x61 interleaving
> Files reviewed:
> - `docs/specs/2026-05-16-ble-parser-battery-fix-design.md`
> - `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleManager.kt`
> - `mobile/app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt`
> - `mobile/app/src/main/java/ru/skatelab/capture/data/ble/Wt901Parser.kt`
> - `mobile/app/src/main/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCase.kt`
> - `mobile/app/src/main/java/ru/skatelab/capture/presentation/recording/RecordingViewModel.kt`
> - `mobile/app/src/test/java/ru/skatelab/capture/data/ble/Wt901ParserTest.kt`

---

## 1. Register Read/Write Flow Analysis

### 1.1 End-to-end trace

```
UI / ViewModel
    |
    v
BleRepositoryImpl.readBattery(sensorId)          (coroutine, any dispatcher)
    |
    v
BleManager.readRegisterResponse(sensorId, 0x04)
    |-- find address from addressToSensorId (ConcurrentHashMap)
    |-- writeBytes(address, Wt901Commander.readRegister(0x04))
    |       |-- workHandler.post { gatt.writeCharacteristic(char) }
    |       v
    |   Android BLE stack → HCI → sensor
    |       v
    |   sensor processes command → sends 0x71 response
    |       v
    |   onCharacteristicChanged(Binder thread)
    |       |-- bytes.copyOf() // IMMEDIATE copy
    |       |-- workHandler.post { parser.feed(bytes, arrivalNs) }
    |       v
    |   Wt901Parser.feed() // workThread
    |       |-- appendToBuffer(bytes)
    |       |-- parse frames in buffer
    |       |-- if 0x71: parseRegisterReadFrame()
    |           |-- onRegisterRead?.invoke(RegisterReadResult(reg, data))
    |               v
    |           _registerReadResults.tryEmit(address to result)
    |               v
    |   SharedFlow broadcast
    |       v
    |-- withTimeoutOrNull(2000ms) {
    |       _registerReadResults.first { (addr, r) ->
    |           addr == address && r.register == 0x04
    |       }.second
    |   }
    v
Result<ShortArray> → BleRepositoryImpl maps to Int (battery %)
```

### 1.2 Key observations

- **BLE writes and parsing are serialized on `workHandler`** (`HandlerThread("BLE-Work")`). This is correct and matches the WT901BLECL reference pattern.
- **BLE notification bytes are copied immediately** on the Binder thread (`bytes.copyOf()`) before posting to `workHandler`. This prevents the Android BLE stack from reusing the buffer.
- **`writeBytes` is fire-and-forget** (non-blocking, posted to handler). The coroutine suspends on `_registerReadResults.first {}` while the write is in flight.
- **`readRegisterResponse` uses `withTimeoutOrNull(2000L)`**. The default 2-second timeout is generous but can still fail under heavy 0x61 streaming load if the BLE notification queue is deep.

---

## 2. SharedFlow Subscription & Race Condition Analysis

### 2.1 Subscription mechanism

```kotlin
val result = withTimeoutOrNull(timeoutMs) {
    _registerReadResults.first { (addr, r) ->
        addr == address && r.register == register
    }.second
}
```

- `first { predicate }` is a **suspending terminal operator**. It creates a new collector on the SharedFlow, waits until an emission matches the predicate, then returns that value and **cancels the collection**.
- It does **NOT** consume non-matching emissions — it skips them and keeps waiting.
- Since `_registerReadResults` has `extraBufferCapacity = 8` and `replay = 0` (default), it is a **hot broadcast channel** with a small buffer but no replay.

### 2.2 Can multiple register reads coexist?

**Yes, but with caveats.**

`ReadSensorInfoUseCase` launches **4 concurrent `async` coroutines** for the same sensor:

```kotlin
coroutineScope {
    val deviceIdDeferred = async { bleRepository.readDeviceId(sensorId).getOrDefault("") }
    val firmwareDeferred = async { bleRepository.readFirmwareVersion(sensorId).getOrDefault("") }
    val batteryPercentDeferred = async { bleRepository.readBattery(sensorId).getOrDefault(0) }
    val batteryMvDeferred = async { bleRepository.readBatteryMv(sensorId).getOrDefault(0) }
}
```

This creates 4 concurrent calls to `BleManager.readRegisterResponse()`, each subscribing to `_registerReadResults` with a different `register` filter.

**Scenario — all 4 in flight:**

1. Coroutine A subscribes for `register == 0x68` (device ID).
2. Coroutine B subscribes for `register == 0x60` (firmware).
3. Coroutine C subscribes for `register == 0x04` (battery — currently wrong register).
4. Coroutine D subscribes for `register == 0x64` (battery mV).

When a `0x71` response for `0x68` is emitted:
- **All 4 collectors** receive the emission.
- Only A's predicate matches. A returns the result and cancels its collector.
- B, C, D skip the emission and keep waiting.

When `0x71` for `0x60` arrives:
- B matches and returns.
- C and D keep waiting.

**This works correctly** in principle because SharedFlow broadcasts to all active collectors, and `first { predicate }` is selective.

### 2.3 Race conditions identified

#### Race 1: Response arrives before subscription

```kotlin
writeBytes(address, Wt901Commander.readRegister(register))
// <-- response could arrive HERE if write was buffered and sensor is fast

val result = withTimeoutOrNull(timeoutMs) {
    _registerReadResults.first { ... }
}
```

- `writeBytes` posts to `workHandler`. The actual GATT write happens on the work thread.
- `first {}` suspends immediately after.
- In practice, the BLE stack + sensor processing + round-trip time is > 10ms, while coroutine suspension is < 1ms. The subscription almost always wins.
- **Risk: LOW** for a single read. **Risk: MEDIUM** if multiple reads are queued rapidly on the work thread, because the parser may emit responses faster than the coroutines subscribe.

#### Race 2: One collector "steals" another's response due to identical register

`readBattery()` and `readBatteryMv()` both read register `0x64` (after the fix):

```kotlin
override suspend fun readBattery(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)
    return result.map { voltageToPercent(it[0].toInt()) }
}

override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> {
    val result = bleManager.readRegisterResponse(sensorId, 0x64)
    return result.map { it[0].toInt() * 100 }
}
```

Both `async` blocks in `ReadSensorInfoUseCase` call `readRegisterResponse(sensorId, 0x64)` concurrently. They subscribe with the **same** `(address, 0x64)` filter.

When the first `0x71` for `0x64` arrives:
- Both collectors match the predicate.
- **Only one** gets the emission (SharedFlow emission to multiple collectors is broadcast, but `first {}` is a race — whichever collector processes it first wins).
- The other collector waits for a **second** `0x71` for `0x64`, which never comes (only one command was sent per call, but wait — both calls send a command).

Actually, both calls send `readRegister(0x64)` via `writeBytes`. So **two commands** are sent, and **two responses** are expected. The race is between which collector gets which response. Since both responses are identical, this is benign.

**However**, if one response is lost or the sensor coalesces them (unlikely), one collector would timeout.

#### Race 3: Timeout under streaming load

During 200Hz IMU streaming, BLE notifications arrive every 5ms. The Android BLE stack may queue notifications. A single 20-byte `0x71` response must be queued behind pending `0x61` frames.

With 4 concurrent register reads, the last command's response may be delayed by:
- Queue depth of pending 0x61 notifications
- 4 write operations serialized on `workHandler`
- Parser processing time for accumulated bytes

The 2-second timeout should absorb this, but if the BLE connection is marginal or the queue is deep, timeouts are possible.

### 2.4 No cancellation mechanism for stale reads

If a register read is in flight and the coroutine is cancelled (e.g., user navigates away), the `withTimeoutOrNull` block returns `null`, but:
- The BLE write was already sent.
- The sensor will still respond with `0x71`.
- The response arrives on `_registerReadResults`, but there is no collector for it.
- If the buffer is full (`extraBufferCapacity = 8`), `tryEmit` may drop the response.
- If a **new** register read starts later, it may receive the stale response if it matches the register. If not, the stale response is skipped.

**Impact: LOW** — stale responses are harmless if they don't match the current request's register.

---

## 3. 0x71 / 0x61 Interleaving Feasibility

### 3.1 Do they arrive on the same characteristic?

**Yes.** The WT901 sends all data notifications on the same characteristic (`FFE4`):

```kotlin
val NOTIFY_UUID: UUID = UUID.fromString("0000FFE4-0000-1000-8000-00805F9A34FB")
```

The sensor does not use separate characteristics for IMU streaming and register responses. Both `0x61` (combined IMU) and `0x71` (register read response) are sent as notifications on `FFE4`.

### 3.2 Can they interleave at the BLE protocol level?

**Yes.** BLE notifications are sent as individual ATT PDUs. The sensor firmware can interleave a `0x71` response between `0x61` frames at any time. From the Android app's perspective, `onCharacteristicChanged` is called for each notification, delivering a `ByteArray` containing the frame.

### 3.3 Can they interleave inside a single `ByteArray`?

**Theoretically yes, but unlikely.** The standard BLE MTU is 23 bytes. A single notification can carry up to 20 bytes of payload. A `0x61` frame is exactly 20 bytes. A `0x71` frame (after the fix) is also 20 bytes. So each notification contains exactly one frame. Interleaving within a single `ByteArray` would only happen if the MTU is negotiated higher (e.g., 185 bytes), allowing multiple frames per notification.

The parser (`Wt901Parser.feed()`) is designed for this:
- It appends all incoming bytes to a `buffer`.
- It parses complete frames from the buffer in a loop.
- It handles partial frames across notifications.

### 3.4 Parser behavior with interleaved 0x71

Current parser logic (pre-fix):

```kotlin
while (bufferSize >= INDIVIDUAL_FRAME_SIZE) {
    val frameType = buffer[1]
    val frameSize = if (frameType == TYPE_COMBINED) COMBINED_FRAME_SIZE else INDIVIDUAL_FRAME_SIZE
    // INDIVIDUAL_FRAME_SIZE = 11, so 0x71 uses 11
}
```

When a 20-byte `0x71` arrives:
1. Parser sees `0x55` header.
2. Reads `frameType = 0x71`.
3. Uses `frameSize = 11` (wrong).
4. Validates checksum (likely fails because checksum is at byte 10, but data is different).
5. If checksum happens to pass, it parses garbage from `buffer[3..8]`.
6. Shifts buffer by 11, leaving 9 residual bytes.
7. Next iteration: buffer starts with the remaining 9 bytes of the `0x71` frame, which has no `0x55` header.
8. `findFrameHeader()` scans forward, finds the next `0x55` (if any) at an unknown offset.
9. **Desync.** All subsequent frames are misaligned until a lucky resync occurs.

**This is the root cause of the timeout.** The `0x71` response is swallowed by the parser, never emitted to `_registerReadResults`, so `first {}` waits until timeout.

### 3.5 Post-fix parser behavior

After applying the spec fix:

```kotlin
val frameSize = when (frameType) {
    TYPE_COMBINED -> COMBINED_FRAME_SIZE
    TYPE_REG_READ -> REG_READ_FRAME_SIZE   // 20
    else -> INDIVIDUAL_FRAME_SIZE
}
```

With the fix:
1. Parser sees `0x71`, uses `frameSize = 20`.
2. If `bufferSize < 20`, it breaks and waits for more data.
3. If `bufferSize >= 20`, it parses the full frame.
4. For `0x71`, it does **not** validate checksum (the current code only validates checksum for individual frames: `else if (!isChecksumValid())`). Wait — `isChecksumValid()` is called for `frameType != TYPE_COMBINED`. For `0x71`, it will call `isChecksumValid()`, which sums bytes[0..9] and compares to bytes[10]. But a 20-byte `0x71` has more data. The checksum is still at byte 10 (per 11-byte frame format), but the frame is 20 bytes. The spec says BLE `0x71` is 20 bytes and may not have the same checksum semantics.

**CRITICAL QUESTION**: Does the 20-byte BLE `0x71` frame have a checksum at byte 10?

Looking at the spec document:
- BLE 0x71 format: `[0x55][0x71][RegL][RegH][d0L][d0H]...[d7L][d7H]` = 20 bytes.
- The current `isChecksumValid()` sums bytes[0..9] and checks byte[10].
- If the 20-byte frame uses the same checksum (sum of first 10 bytes, checksum at byte 10), then the checksum is at byte 10, and bytes[11..19] are additional data. The parser should validate checksum using the first 11 bytes, then extract data from bytes[4..19].

However, the current code shifts by `frameSize` after parsing. If `frameSize = 20`, it shifts by 20. The checksum validation uses `INDIVIDUAL_FRAME_SIZE - 1 = 10`, so it checks byte 10. This is fine **IF** the checksum is still at byte 10 in the 20-byte format.

But wait — the spec says the current `parseRegisterReadFrame` reads `ShortArray(3)` from `buffer[3..8]`. After the fix, it should read `ShortArray(8)` from `buffer[4..19]`. The checksum at byte 10 is between data bytes 2 and 3 (`d2L/d2H` and `d3L/d3H`). This means the checksum byte is **inside** the data payload in the 20-byte view. This is extremely suspicious.

**Reality check**: The WitMotion WT901 BLE protocol likely does NOT use the 11-byte individual-frame checksum for the 20-byte `0x71`. The 20-byte format is probably `[0x55][0x71][RegL][RegH][16 data bytes][checksum?]` or simply no checksum.

The spec document says: "BLE 0x71 format is `[0x55][0x71][RegL][RegH][d0L][d0H]...[d7L][d7H]` = 20 bytes." It does not mention a checksum.

**Conclusion**: For 20-byte `0x71`, the parser should **skip checksum validation** (like `0x61`) or use a different checksum position. The current code calls `isChecksumValid()` for all non-combined frames, which will likely fail for 20-byte `0x71` because byte 10 is data, not checksum.

**Recommendation**: In the `when` block for `TYPE_REG_READ`, skip checksum validation (or validate only if we know the checksum position). The safest approach is to treat `0x71` like `0x61` — no checksum, rely on frame structure.

---

## 4. Thread Safety Analysis

### 4.1 Parser thread safety

```kotlin
private val parsers = ConcurrentHashMap<String, Wt901Parser>()
```

- `Wt901Parser` instances are created lazily inside `workHandler.post {}` in `onCharacteristicChanged`.
- `feed()` is only called from `workHandler` (the work thread).
- **Conclusion: Parser is single-threaded per device. No thread-safety issues.**

### 4.2 SharedFlow thread safety

```kotlin
private val _registerReadResults = MutableSharedFlow<Pair<String, RegisterReadResult>>(extraBufferCapacity = 8)
```

- Emission: `tryEmit()` is called from `workHandler` (parsing thread).
- Collection: `first {}` is called from coroutines (e.g., `Dispatchers.IO` or `viewModelScope`).
- `MutableSharedFlow` is thread-safe for both emission and collection.
- **Conclusion: Thread-safe.**

### 4.3 Address map thread safety

```kotlin
private val addressToSensorId = ConcurrentHashMap<String, SensorId>()
```

- `readRegisterResponse` does: `addressToSensorId.entries.find { it.value == sensorId }?.key`
- Iterating `ConcurrentHashMap.entries` is weakly consistent. In practice, this is safe because sensor IDs don't change during a read.
- **However**, a reverse map (`sensorIdToAddress: ConcurrentHashMap<SensorId, String>`) would be more efficient and eliminate the O(n) search.

---

## 5. Parallel/Async Register Read Recommendations

### 5.1 Current approach: 4 concurrent `async` reads

`ReadSensorInfoUseCase` does 4 parallel reads. This is fine **if** the sensor handles multiple register read commands queued on the same connection. The WT901 likely processes them FIFO and responds with `0x71` frames in order.

**Problem**: The responses may be delayed by streaming traffic, and the last read has the highest timeout risk.

### 5.2 Recommended: Serialize register reads per sensor

Add a `Mutex` in `BleManager` (or `BleRepositoryImpl`) to ensure only one register read is in-flight at a time per sensor:

```kotlin
private val readMutexes = ConcurrentHashMap<String, Mutex>()

suspend fun readRegisterResponse(
    sensorId: SensorId,
    register: Int,
    timeoutMs: Long = 2000L,
): Result<ShortArray> {
    val address = ...
    val mutex = readMutexes.getOrPut(address) { Mutex() }
    mutex.withLock {
        writeBytes(address, Wt901Commander.readRegister(register))
        return try {
            val result = withTimeoutOrNull(timeoutMs) {
                _registerReadResults.first { (addr, r) ->
                    addr == address && r.register == register
                }.second
            }
            if (result != null) Result.success(result.data)
            else Result.failure(TimeoutException(...))
        } catch (...) { ... }
    }
}
```

**Benefits:**
- Eliminates race between multiple collectors for the same register.
- Reduces BLE queue pressure.
- Makes timeout behavior predictable.

**Tradeoff:** Slightly slower (4 reads become serial instead of parallel). For device info reads during connect, this is acceptable (~200ms vs ~50ms). For battery polling every 30s, irrelevant.

### 5.3 Use `StateFlow` for battery state

Instead of on-demand `readBattery()` every 30 seconds, maintain a `StateFlow` in `BleRepositoryImpl`:

```kotlin
private val _batteryState = MutableStateFlow<Map<SensorId, Int>>(emptyMap())
val batteryState: StateFlow<Map<SensorId, Int>> = _batteryState.asStateFlow()
```

A dedicated coroutine polls battery and updates the StateFlow. UI collects it reactively.

**Benefits:**
- UI always has the latest cached battery level.
- No coroutine churn for every UI poll.
- Survives configuration changes.

### 5.4 Read battery BEFORE streaming starts

The `RecordingViewModel` starts battery polling (`startBatteryPolling`) when recording begins. At this point, IMU streaming is already active (CCCD enabled on connect).

**Recommendation:** Read battery, firmware, and device ID **once during sensor setup** (right after `ConnectionState.CONNECTED`), before the user starts recording. Store the results in the repository's state flows. During recording, only poll battery periodically.

This avoids register reads during the highest streaming load and gives the user battery info immediately upon connection.

### 5.5 Parallel reads to different registers on the same sensor

With the `Mutex` recommendation, parallel reads are serialized per sensor. However, reads to **different sensors** (LEFT and RIGHT) can still be parallel because they use different `addressToSensorId` entries and different GATT objects.

`ReadSensorInfoUseCase` currently reads from one sensor at a time. If called for both LEFT and RIGHT concurrently (e.g., from two ViewModel coroutines), they are naturally parallel because `BleRepositoryImpl` creates a separate `BleManager` instance? Wait — `BleRepositoryImpl` creates a single `BleManager`:

```kotlin
private val bleManager = BleManager(context, appLogger)
```

So all sensors share the same `BleManager`, but `addressToSensorId` distinguishes them. The `Mutex` should be per-address, not per-`BleManager`.

---

## 6. Specific Code Recommendations

### 6.1 Parser fix (Wt901Parser.kt)

1. Add `REG_READ_FRAME_SIZE = 20`.
2. Update `frameSize` logic in `feed()`:
   ```kotlin
   val frameSize = when (frameType) {
       TYPE_COMBINED -> COMBINED_FRAME_SIZE
       TYPE_REG_READ -> REG_READ_FRAME_SIZE
       else -> INDIVIDUAL_FRAME_SIZE
   }
   ```
3. Update `parseRegisterReadFrame()`:
   ```kotlin
   private fun parseRegisterReadFrame() {
       val reg = buffer[2].toInt() and 0xFF
       val data = ShortArray(8) { i ->
           readInt16LEShort(4 + i * 2)
       }
       onRegisterRead?.invoke(RegisterReadResult(reg, data))
   }
   ```
4. **Skip checksum for `0x71`** in the `when` block or modify the checksum logic:
   ```kotlin
   when (frameType) {
       TYPE_COMBINED -> parseCombinedFrame(arrivalNs)
       TYPE_ACC, TYPE_GYRO, TYPE_QUAT -> processFrame(frameType, arrivalNs)
       TYPE_REG_READ -> {
           parseRegisterReadFrame()
           null
       }
       else -> { shiftBuffer(1); continue }
   }
   ```
   Remove `isChecksumValid()` call for `TYPE_REG_READ`.

### 6.2 Battery fix (BleRepositoryImpl.kt)

1. Fix `readBattery` register: `0x04` → `0x64`.
2. Add `voltageToPercent()` conversion table.
3. Fix `readBatteryMv`: multiply by 100.
4. (Optional) Add `readBattery` cache/state flow.

### 6.3 Add read serialization (BleManager.kt)

Add per-address `Mutex`:

```kotlin
private val readMutexes = ConcurrentHashMap<String, Mutex>()

suspend fun readRegisterResponse(...): Result<ShortArray> {
    val address = ...
    val mutex = readMutexes.getOrPut(address) { Mutex() }
    mutex.withLock {
        writeBytes(address, Wt901Commander.readRegister(register))
        // ... existing withTimeoutOrNull logic
    }
}
```

### 6.4 Update tests (Wt901ParserTest.kt)

1. `parseRegisterReadResponse()`: build a 20-byte `0x71` frame, verify `RegisterReadResult.data.size == 8`.
2. `parseRegisterReadResponseDoesNotInterfereWithImuCycle()`: use 20-byte `0x71` frame.
3. Add test for `0x71` checksumless parsing: a 20-byte `0x71` with arbitrary byte 10 should still parse correctly.
4. Add test for `0x71` followed by `0x61` in the same notification buffer.

### 6.5 Consider increasing SharedFlow buffer

If 4 concurrent reads are kept (without `Mutex`), `extraBufferCapacity = 8` may be tight. Consider `extraBufferCapacity = 16` or `32` to absorb bursts.

### 6.6 Add `sensorIdToAddress` reverse map

```kotlin
private val sensorIdToAddress = ConcurrentHashMap<SensorId, String>()
```

Update in `connect()` and `cleanupDevice()`. Replace `addressToSensorId.entries.find { it.value == sensorId }?.key` with `sensorIdToAddress[sensorId]`.

---

## 7. Summary

| Concern | Status | Risk | Mitigation |
|---|---|---|---|
| 0x71 frame size (11 vs 20) | **BUG** — causes parser desync | HIGH | Fix parser to use `REG_READ_FRAME_SIZE = 20` |
| 0x71/0x61 interleaving | **FEASIBLE** — same characteristic | MEDIUM | Parser buffer handles it; fix frame size first |
| SharedFlow race (same register) | **RACE EXISTS** — 2 collectors for `0x64` | MEDIUM | Add per-address `Mutex` for register reads |
| SharedFlow race (response before subscribe) | **RARE** — subscription is fast | LOW | Acceptable; `Mutex` reduces likelihood |
| Checksum for 20-byte 0x71 | **UNCERTAIN** — likely no checksum | HIGH | Skip checksum validation for `0x71` |
| Timeout during streaming | **POSSIBLE** — queue depth varies | MEDIUM | Increase timeout to 3000ms; read before streaming |
| Thread safety | **OK** — parser on work thread, SharedFlow thread-safe | LOW | None needed |
| Concurrent 4-register reads | **WORKS** but fragile | MEDIUM | Serialize with `Mutex` |
| Battery polling during streaming | **INEFFICIENT** | LOW | Read once on connect; use `StateFlow` cache |

### Immediate action items

1. **Fix parser frame size and data offset** (spec bugs 1, 3).
2. **Skip checksum for 0x71** (parser bug not in spec).
3. **Fix battery register and conversion** (spec bugs 4, 5).
4. **Add `Mutex` in `BleManager.readRegisterResponse`**.
5. **Update tests** to use 20-byte 0x71 frames.
6. **(Optional)** Add `StateFlow` battery cache and read sensor info on connect.
