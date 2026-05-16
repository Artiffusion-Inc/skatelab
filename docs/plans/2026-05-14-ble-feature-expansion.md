# BLE Feature Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add battery mV, Device ID, firmware version, and automatic time configuration to the WT901 BLE stack, with UI display on the scan screen.

**Architecture:** Extend Wt901Commander with time-config commands, add SensorInfo domain model, create two new UseCases (ReadSensorInfoUseCase, ConfigureSensorTimeUseCase), wire automatic time config into TimeSynchronizerImpl, and add sensor info display to BleScanScreen.

**Tech Stack:** Kotlin, Hilt DI, MockK, Coroutines Test, Compose UI

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `app/src/main/java/ru/skatelab/capture/domain/model/SensorInfo.kt` | Domain model: deviceId, firmwareVersion, batteryPercent, batteryMv |
| Create | `app/src/main/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCase.kt` | Fetches SensorInfo from 4 register reads |
| Create | `app/src/main/java/ru/skatelab/capture/domain/usecase/ConfigureSensorTimeUseCase.kt` | Sends time config sequence to sensor |
| Modify | `app/src/main/java/ru/skatelab/capture/data/ble/Wt901Commander.kt` | Add setTimeYearMonth, setTimeHourDay, setTimeSecondMinute, timeConfigSequence |
| Modify | `app/src/main/java/ru/skatelab/capture/domain/repository/BleRepository.kt` | Add readDeviceId, readFirmwareVersion, readBatteryMv, configureSensorTime |
| Modify | `app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt` | Implement new BleRepository methods |
| Modify | `app/src/main/java/ru/skatelab/capture/data/sync/TimeSynchronizerImpl.kt` | Auto time-config before chip-time read |
| Modify | `app/src/main/java/ru/skatelab/capture/di/AppModule.kt` | Bind new UseCases |
| Modify | `app/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt` | Add sensorInfo state + refreshSensorInfo + auto-refresh on connect |
| Modify | `app/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt` | Display SensorInfo in ScanDeviceRow |
| Create | `app/src/test/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCaseTest.kt` | Unit tests for SensorInfo assembly |
| Create | `app/src/test/java/ru/skatelab/capture/domain/usecase/ConfigureSensorTimeUseCaseTest.kt` | Unit tests for time config UseCase |
| Modify | `app/src/test/java/ru/skatelab/capture/data/ble/Wt901CommanderTest.kt` | Tests for new time config commands |
| Modify | `app/src/test/java/ru/skatelab/capture/presentation/ble/BleScanViewModelTest.kt` | Tests for sensorInfo auto-refresh |
| Create | `app/src/test/java/ru/skatelab/capture/data/sync/TimeSynchronizerImplTest.kt` | Tests for auto time-config trigger |

---

## Wave 1: Domain Model + Wt901Commander

### Task 1: SensorInfo domain model

**Files:**

- Create: `app/src/main/java/ru/skatelab/capture/domain/model/SensorInfo.kt`

- [ ] **Step 1: Create SensorInfo.kt**

```kotlin
package ru.skatelab.capture.domain.model

data class SensorInfo(
    val deviceId: String,
    val firmwareVersion: String,
    val batteryPercent: Int,
    val batteryMv: Int,
)
```

- [ ] **Step 2: Compile to verify**

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/domain/model/SensorInfo.kt
git commit -m "feat(android): add SensorInfo domain model"
```

---

### Task 2: Wt901Commander time-config commands

**Files:**

- Modify: `app/src/main/java/ru/skatelab/capture/data/ble/Wt901Commander.kt:67-82` (after setRate, before restart)
- Modify: `app/src/test/java/ru/skatelab/capture/data/ble/Wt901CommanderTest.kt`

- [ ] **Step 1: Write failing tests in Wt901CommanderTest.kt**

Add after the last `@Test` function in `Wt901CommanderTest.kt`:

```kotlin
@Test
fun setTimeYearMonthCommand() {
    val bytes = Wt901Commander.setTimeYearMonth(2026, 5)
    assertArrayEquals(
        byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x30, 0x05, (2026 - 2000).toByte()),
        bytes,
    )
}

@Test
fun setTimeHourDayCommand() {
    val bytes = Wt901Commander.setTimeHourDay(14, 15)
    assertArrayEquals(
        byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x31, 14, 15),
        bytes,
    )
}

@Test
fun setTimeSecondMinuteCommand() {
    val bytes = Wt901Commander.setTimeSecondMinute(30, 45)
    assertArrayEquals(
        byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x32, 30, 45),
        bytes,
    )
}

@Test
fun timeConfigSequenceLength() {
    val seq = Wt901Commander.timeConfigSequence()
    assertEquals("Time config sequence should have 5 steps", 5, seq.size)
}

@Test
fun timeConfigSequenceContainsCorrectCommands() {
    val seq = Wt901Commander.timeConfigSequence()
    assertArrayEquals(Wt901Commander.unlock(), seq[0].bytes)
    // Steps 1-3 are time-set commands (bytes vary by current time)
    assertArrayEquals(Wt901Commander.save(), seq[4].bytes)
}

@Test
fun timeConfigSequenceDelays() {
    val seq = Wt901Commander.timeConfigSequence()
    assertEquals(50L, seq[0].delayAfterMs)   // unlock → 50ms
    assertEquals(100L, seq[1].delayAfterMs)  // setTimeYearMonth → 100ms
    assertEquals(100L, seq[2].delayAfterMs)  // setTimeHourDay → 100ms
    assertEquals(100L, seq[3].delayAfterMs)  // setTimeSecondMinute → 100ms
    assertEquals(500L, seq[4].delayAfterMs)  // save → 500ms
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mobile && ./gradlew :app:compileDebugUnitTestKotlin 2>&1 | tail -5`
Expected: Compilation error — `setTimeYearMonth`, `setTimeHourDay`, `setTimeSecondMinute`, `timeConfigSequence` not found.

- [ ] **Step 3: Implement the commands in Wt901Commander.kt**

Add after `setRate()` and before `restart()`, inside the `object Wt901Commander` body:

```kotlin
/** Set sensor date — year/month register (0x30). */
fun setTimeYearMonth(
    year: Int,
    month: Int,
): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x30, month.toByte(), (year - 2000).toByte())

/** Set sensor date — hour/day register (0x31). */
fun setTimeHourDay(
    hour: Int,
    day: Int,
): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x31, hour.toByte(), day.toByte())

/** Set sensor time — second/minute register (0x32). */
fun setTimeSecondMinute(
    second: Int,
    minute: Int,
): ByteArray = byteArrayOf(CMD_PREFIX_0, CMD_PREFIX_1, 0x32, second.toByte(), minute.toByte())

/**
 * Time configuration sequence: writes current Android time to sensor.
 * Must be called BEFORE streaming starts (WT901 ignores register writes during streaming).
 * Sequence: unlock → setTimeYearMonth → setTimeHourDay → setTimeSecondMinute → save
 */
fun timeConfigSequence(): List<CommandStep> {
    val now = java.util.Calendar.getInstance()
    return listOf(
        CommandStep(unlock(), DELAY_AFTER_UNLOCK_MS),
        CommandStep(setTimeYearMonth(now.get(java.util.Calendar.YEAR), now.get(java.util.Calendar.MONTH) + 1), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(setTimeHourDay(now.get(java.util.Calendar.HOUR_OF_DAY), now.get(java.util.Calendar.DAY_OF_MONTH)), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(setTimeSecondMinute(now.get(java.util.Calendar.SECOND), now.get(java.util.Calendar.MINUTE)), DELAY_BETWEEN_CONFIG_MS),
        CommandStep(save(), DELAY_AFTER_SAVE_MS),
    )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "*.Wt901CommanderTest" 2>&1 | tail -5`
Expected: All tests PASS

- [ ] **Step 5: Run ktlint**

Run: `cd mobile && ./gradlew :app:ktlintCheck 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL. If failures, run `./gradlew :app:ktlintFormat` then re-check.

- [ ] **Step 6: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/data/ble/Wt901Commander.kt app/src/test/java/ru/skatelab/capture/data/ble/Wt901CommanderTest.kt
git commit -m "feat(android): add WT901 time-config commands to Wt901Commander"
```

---

## Wave 2: BleRepository + UseCases

### Task 3: BleRepository new methods

**Files:**

- Modify: `app/src/main/java/ru/skatelab/capture/domain/repository/BleRepository.kt:38-41` (after readChipTime)
- Modify: `app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt:83-98` (after readChipTime)

- [ ] **Step 1: Add new methods to BleRepository interface**

After `readChipTime`, add:

```kotlin
suspend fun readDeviceId(sensorId: SensorId): Result<String>

suspend fun readFirmwareVersion(sensorId: SensorId): Result<String>

suspend fun readBatteryMv(sensorId: SensorId): Result<Int>

suspend fun configureSensorTime(sensorId: SensorId): Result<Unit>
```

- [ ] **Step 2: Implement in BleRepositoryImpl**

After `readChipTime` override, add:

```kotlin
override suspend fun readDeviceId(sensorId: SensorId): Result<String> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x68).getOrThrow()
        "%04X%04X%04X".format(data[0].toInt() and 0xFFFF, data[1].toInt() and 0xFFFF, data[2].toInt() and 0xFFFF)
    }

override suspend fun readFirmwareVersion(sensorId: SensorId): Result<String> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x60).getOrThrow()
        val major = (data[0].toInt() and 0xFFFF) shr 8
        val minor = data[0].toInt() and 0xFF
        val patch = (data[1].toInt() and 0xFF00) shr 8
        "$major.$minor.$patch"
    }

override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
    runCatching {
        val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
        data[0].toInt() and 0xFFFF
    }

override suspend fun configureSensorTime(sensorId: SensorId): Result<Unit> =
    runCatching {
        bleManager.sendSequence(sensorId, Wt901Commander.timeConfigSequence())
    }
```

- [ ] **Step 3: Compile to verify**

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Run ktlint, fix if needed**

Run: `cd mobile && ./gradlew :app:ktlintFormat :app:ktlintCheck 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/domain/repository/BleRepository.kt app/src/main/java/ru/skatelab/capture/data/ble/BleRepositoryImpl.kt
git commit -m "feat(android): add readDeviceId, readFirmwareVersion, readBatteryMv, configureSensorTime to BleRepository"
```

---

### Task 4: ReadSensorInfoUseCase

**Files:**

- Create: `app/src/main/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCase.kt`
- Create: `app/src/test/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCaseTest.kt`

- [ ] **Step 1: Write failing test**

```kotlin
package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class ReadSensorInfoUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: ReadSensorInfoUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = ReadSensorInfoUseCase(bleRepository)
    }

    @Test
    fun `success returns SensorInfo with all fields`() =
        runTest {
            coEvery { bleRepository.readDeviceId(SensorId.LEFT) } returns Result.success("A3F20012ABCD")
            coEvery { bleRepository.readFirmwareVersion(SensorId.LEFT) } returns Result.success("1.2.3")
            coEvery { bleRepository.readBattery(SensorId.LEFT) } returns Result.success(85)
            coEvery { bleRepository.readBatteryMv(SensorId.LEFT) } returns Result.success(3850)

            val result = useCase(SensorId.LEFT)

            assertEquals("A3F20012ABCD", result.getOrThrow().deviceId)
            assertEquals("1.2.3", result.getOrThrow().firmwareVersion)
            assertEquals(85, result.getOrThrow().batteryPercent)
            assertEquals(3850, result.getOrThrow().batteryMv)
        }

    @Test
    fun `partial failure returns SensorInfo with defaults for failed reads`() =
        runTest {
            coEvery { bleRepository.readDeviceId(SensorId.LEFT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readFirmwareVersion(SensorId.LEFT) } returns Result.success("1.0.0")
            coEvery { bleRepository.readBattery(SensorId.LEFT) } returns Result.success(50)
            coEvery { bleRepository.readBatteryMv(SensorId.LEFT) } returns Result.failure(Exception("err"))

            val result = useCase(SensorId.LEFT)

            assertEquals("", result.getOrThrow().deviceId)
            assertEquals("1.0.0", result.getOrThrow().firmwareVersion)
            assertEquals(50, result.getOrThrow().batteryPercent)
            assertEquals(0, result.getOrThrow().batteryMv)
        }

    @Test
    fun `all failures returns SensorInfo with all defaults`() =
        runTest {
            coEvery { bleRepository.readDeviceId(SensorId.RIGHT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readFirmwareVersion(SensorId.RIGHT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readBattery(SensorId.RIGHT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readBatteryMv(SensorId.RIGHT) } returns Result.failure(Exception("err"))

            val result = useCase(SensorId.RIGHT)

            val info = result.getOrThrow()
            assertEquals("", info.deviceId)
            assertEquals("", info.firmwareVersion)
            assertEquals(0, info.batteryPercent)
            assertEquals(0, info.batteryMv)
        }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :app:compileDebugUnitTestKotlin 2>&1 | tail -5`
Expected: Compilation error — `ReadSensorInfoUseCase` not found.

- [ ] **Step 3: Implement ReadSensorInfoUseCase**

```kotlin
package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository

class ReadSensorInfoUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
    ) {
        suspend operator fun invoke(sensorId: SensorId): Result<SensorInfo> =
            runCatching {
                coroutineScope {
                    val deviceIdDeferred = async { bleRepository.readDeviceId(sensorId).getOrDefault("") }
                    val firmwareDeferred = async { bleRepository.readFirmwareVersion(sensorId).getOrDefault("") }
                    val batteryPercentDeferred = async { bleRepository.readBattery(sensorId).getOrDefault(0) }
                    val batteryMvDeferred = async { bleRepository.readBatteryMv(sensorId).getOrDefault(0) }
                    SensorInfo(
                        deviceId = deviceIdDeferred.await(),
                        firmwareVersion = firmwareDeferred.await(),
                        batteryPercent = batteryPercentDeferred.await(),
                        batteryMv = batteryMvDeferred.await(),
                    )
                }
            }
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "*.ReadSensorInfoUseCaseTest" 2>&1 | tail -5`
Expected: All tests PASS

- [ ] **Step 5: Run ktlint, fix if needed**

Run: `cd mobile && ./gradlew :app:ktlintFormat :app:ktlintCheck 2>&1 | tail -3`

- [ ] **Step 6: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCase.kt app/src/test/java/ru/skatelab/capture/domain/usecase/ReadSensorInfoUseCaseTest.kt
git commit -m "feat(android): add ReadSensorInfoUseCase — parallel register reads"
```

---

### Task 5: ConfigureSensorTimeUseCase

**Files:**

- Create: `app/src/main/java/ru/skatelab/capture/domain/usecase/ConfigureSensorTimeUseCase.kt`
- Create: `app/src/test/java/ru/skatelab/capture/domain/usecase/ConfigureSensorTimeUseCaseTest.kt`

- [ ] **Step 1: Write failing test**

```kotlin
package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class ConfigureSensorTimeUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: ConfigureSensorTimeUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = ConfigureSensorTimeUseCase(bleRepository)
    }

    @Test
    fun `success calls configureSensorTime`() =
        runTest {
            coEvery { bleRepository.configureSensorTime(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)

            assert(result.isSuccess)
            coVerify(exactly = 1) { bleRepository.configureSensorTime(SensorId.LEFT) }
        }

    @Test
    fun `failure propagates error`() =
        runTest {
            coEvery { bleRepository.configureSensorTime(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("GATT error"))

            val result = useCase(SensorId.RIGHT)

            assert(result.isFailure)
        }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :app:compileDebugUnitTestKotlin 2>&1 | tail -5`
Expected: Compilation error.

- [ ] **Step 3: Implement ConfigureSensorTimeUseCase**

```kotlin
package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class ConfigureSensorTimeUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
    ) {
        suspend operator fun invoke(sensorId: SensorId): Result<Unit> = bleRepository.configureSensorTime(sensorId)
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "*.ConfigureSensorTimeUseCaseTest" 2>&1 | tail -5`
Expected: All tests PASS

- [ ] **Step 5: Register UseCases in AppModule**

Add to `AppModule.kt` — no `@Binds` needed for `@Inject constructor` classes. Hilt auto-provides them. Just verify compilation.

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Run ktlint, fix if needed**

Run: `cd mobile && ./gradlew :app:ktlintFormat :app:ktlintCheck 2>&1 | tail -3`

- [ ] **Step 7: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/domain/usecase/ConfigureSensorTimeUseCase.kt app/src/test/java/ru/skatelab/capture/domain/usecase/ConfigureSensorTimeUseCaseTest.kt
git commit -m "feat(android): add ConfigureSensorTimeUseCase"
```

---

## Wave 3: TimeSynchronizer auto time-config

### Task 6: Auto time-config in TimeSynchronizerImpl

**Files:**

- Modify: `app/src/main/java/ru/skatelab/capture/data/sync/TimeSynchronizerImpl.kt`
- Create: `app/src/test/java/ru/skatelab/capture/data/sync/TimeSynchronizerImplTest.kt`

Current `TimeSynchronizerImpl`:
```kotlin
class TimeSynchronizerImpl @Inject constructor(
    private val periodicTimeSync: PeriodicTimeSync,
    private val timeSyncManager: TimeSyncManager,
) : TimeSynchronizer {
    override fun sync(scope: CoroutineScope) = periodicTimeSync.sync(scope)
    override suspend fun awaitSync() = periodicTimeSync.awaitSync()
    override fun stop() = periodicTimeSync.stop()
    override fun getOffset(sensorId: SensorId): Long = timeSyncManager.getOffset(sensorId)
}
```

After changes, `sync()` will first attempt `configureSensorTime()` for each sensor where offset is unknown (=0, first sync) or exceeds 1s, then (sequentially) delegate to `periodicTimeSync.sync()`.

**Design decision:** `offset=0` means "never synced" → must configure time. `abs(offset) < 1s && offset != 0` means clock is close enough → skip. Time-config runs **sequentially before** `periodicTimeSync.sync()` to avoid race condition (WT901 ignores register reads while processing writes).

- [ ] **Step 1: Write failing test**

```kotlin
package ru.skatelab.capture.data.sync

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.usecase.ConfigureSensorTimeUseCase

@OptIn(ExperimentalCoroutinesApi::class)
class TimeSynchronizerImplTest {
    private lateinit var periodicTimeSync: PeriodicTimeSync
    private lateinit var timeSyncManager: TimeSyncManager
    private lateinit var configureSensorTimeUseCase: ConfigureSensorTimeUseCase
    private lateinit var synchronizer: TimeSynchronizerImpl

    @Before
    fun setUp() {
        periodicTimeSync = mockk(relaxed = true)
        timeSyncManager = mockk(relaxed = true)
        configureSensorTimeUseCase = mockk(relaxed = true)
        synchronizer = TimeSynchronizerImpl(periodicTimeSync, timeSyncManager, configureSensorTimeUseCase)
    }

    @Test
    fun `sync calls configureSensorTime when offset exceeds 1 second`() =
        runTest {
            coEvery { timeSyncManager.getOffset(SensorId.LEFT) } returns 2_000_000_000L
            coEvery { timeSyncManager.getOffset(SensorId.RIGHT) } returns 500_000_000L
            coEvery { configureSensorTimeUseCase(SensorId.LEFT) } returns Result.success(Unit)

            synchronizer.sync(this)
            advanceUntilIdle()

            coVerify(exactly = 1) { configureSensorTimeUseCase(SensorId.LEFT) }
            coVerify(exactly = 0) { configureSensorTimeUseCase(SensorId.RIGHT) }
        }

    @Test
    fun `sync calls configureSensorTime when offset is zero (first sync)`) =
        runTest {
            coEvery { timeSyncManager.getOffset(SensorId.LEFT) } returns 0L
            coEvery { timeSyncManager.getOffset(SensorId.RIGHT) } returns 0L
            coEvery { configureSensorTimeUseCase(any()) } returns Result.success(Unit)

            synchronizer.sync(this)
            advanceUntilIdle()

            // offset=0 means never synced → always configure time
            coVerify(exactly = 1) { configureSensorTimeUseCase(SensorId.LEFT) }
            coVerify(exactly = 1) { configureSensorTimeUseCase(SensorId.RIGHT) }
        }

    @Test
    fun `sync skips configureSensorTime when offset under 1 second and non-zero`() =
        runTest {
            coEvery { timeSyncManager.getOffset(SensorId.LEFT) } returns 500_000_000L
            coEvery { timeSyncManager.getOffset(SensorId.RIGHT) } returns 800_000_000L

            synchronizer.sync(this)
            advanceUntilIdle()

            coVerify(exactly = 0) { configureSensorTimeUseCase(any()) }
        }

    @Test
    fun `sync always delegates to periodicTimeSync after time-config`() =
        runTest {
            coEvery { timeSyncManager.getOffset(any()) } returns 500_000_000L // offset < 1s, non-zero

            synchronizer.sync(this)
            advanceUntilIdle()

            verify(exactly = 1) { periodicTimeSync.sync(any()) }
        }

    @Test
    fun `stop delegates to periodicTimeSync`() {
        synchronizer.stop()
        verify(exactly = 1) { periodicTimeSync.stop() }
    }

    @Test
    fun `getOffset delegates to timeSyncManager`() {
        synchronizer.getOffset(SensorId.LEFT)
        verify(exactly = 1) { timeSyncManager.getOffset(SensorId.LEFT) }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :app:compileDebugUnitTestKotlin 2>&1 | tail -5`
Expected: Compilation error — `TimeSynchronizerImpl` constructor mismatch (no `configureSensorTimeUseCase` param).

- [ ] **Step 3: Implement changes in TimeSynchronizerImpl**

Replace the entire file:

```kotlin
package ru.skatelab.capture.data.sync

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.service.TimeSynchronizer
import ru.skatelab.capture.domain.usecase.ConfigureSensorTimeUseCase

@Singleton
class TimeSynchronizerImpl
    @Inject
    constructor(
        private val periodicTimeSync: PeriodicTimeSync,
        private val timeSyncManager: TimeSyncManager,
        private val configureSensorTimeUseCase: ConfigureSensorTimeUseCase,
    ) : TimeSynchronizer {
        companion object {
            private const val OFFSET_THRESHOLD_NS = 1_000_000_000L // 1 second
        }

        override fun sync(scope: CoroutineScope) {
            scope.launch {
                // Auto time-config: write Android time to sensor if offset is
                // unknown (=0, first sync) or exceeds 1 second.
                // Runs BEFORE periodicTimeSync to avoid race — WT901 ignores
                // register reads while processing time-config writes.
                for (sensorId in listOf(SensorId.LEFT, SensorId.RIGHT)) {
                    val offset = timeSyncManager.getOffset(sensorId)
                    if (offset == 0L || kotlin.math.abs(offset) > OFFSET_THRESHOLD_NS) {
                        configureSensorTimeUseCase(sensorId).onFailure {
                            // Best effort — proceed with offset-based sync
                        }
                    }
                }
                periodicTimeSync.sync(scope)
            }
        }

        override suspend fun awaitSync() = periodicTimeSync.awaitSync()

        override fun stop() = periodicTimeSync.stop()

        override fun getOffset(sensorId: SensorId): Long = timeSyncManager.getOffset(sensorId)
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "*.TimeSynchronizerImplTest" 2>&1 | tail -5`
Expected: All tests PASS

- [ ] **Step 5: Update RecordingViewModelTest — TimeSynchronizerImpl constructor changed**

In `RecordingViewModelTest.kt`, the `timeSynchronizer` mock is of type `TimeSynchronizer` (the interface), so no test changes needed. Verify:

Run: `cd mobile && ./gradlew :app:testDebugUnitTest 2>&1 | tail -5`
Expected: All tests PASS

- [ ] **Step 6: Run ktlint, fix if needed**

Run: `cd mobile && ./gradlew :app:ktlintFormat :app:ktlintCheck 2>&1 | tail -3`

- [ ] **Step 7: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/data/sync/TimeSynchronizerImpl.kt app/src/test/java/ru/skatelab/capture/data/sync/TimeSynchronizerImplTest.kt
git commit -m "feat(android): auto time-config in TimeSynchronizerImpl when offset > 1s"
```

---

## Wave 4: ViewModel + UI

### Task 7: BleScanViewModel sensorInfo

**Files:**

- Modify: `app/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt`
- Modify: `app/src/test/java/ru/skatelab/capture/presentation/ble/BleScanViewModelTest.kt`

- [ ] **Step 1: Add ReadSensorInfoUseCase to BleScanViewModel constructor**

Add `readSensorInfoUseCase: ReadSensorInfoUseCase` as a constructor parameter, after `appLogger: Logger`.

- [ ] **Step 2: Add sensorInfo state and refreshSensorInfo method**

Add to the ViewModel body:

```kotlin
private val _sensorInfo = MutableStateFlow<Map<SensorId, SensorInfo?>>(emptyMap())
val sensorInfo: StateFlow<Map<SensorId, SensorInfo?>> = _sensorInfo

init {
    viewModelScope.launch {
        connectionState.collect { stateMap ->
            for ((sensorId, state) in stateMap) {
                if (state == BleRepository.ConnectionState.CONNECTED && _sensorInfo.value[sensorId] == null) {
                    refreshSensorInfo(sensorId)
                }
            }
        }
    }
}

fun refreshSensorInfo(sensorId: SensorId) {
    viewModelScope.launch {
        val result = readSensorInfoUseCase(sensorId)
        if (result.isSuccess) {
            _sensorInfo.value = _sensorInfo.value + (sensorId to result.getOrThrow())
        }
    }
}
```

- [ ] **Step 3: Write test for auto-refresh on connect**

Add to `BleScanViewModelTest.kt`. Update the `setUp` method to include `readSensorInfoUseCase`:

```kotlin
private lateinit var readSensorInfoUseCase: ReadSensorInfoUseCase

// In setUp:
readSensorInfoUseCase = mockk(relaxed = true)

// Update viewModel constructor call to include readSensorInfoUseCase
```

Add test:

```kotlin
@Test
fun `auto-refresh sensorInfo on connect`() =
    testScope.runTest {
        val info = SensorInfo(deviceId = "A3F2", firmwareVersion = "1.0", batteryPercent = 85, batteryMv = 3850)
        coEvery { readSensorInfoUseCase(SensorId.LEFT) } returns Result.success(info)

        connectionStateFlow.value = mapOf(SensorId.LEFT to BleRepository.ConnectionState.CONNECTED)
        advanceUntilIdle()

        assertEquals(info, viewModel.sensorInfo.value[SensorId.LEFT])
    }
```

- [ ] **Step 4: Run tests**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest --tests "*.BleScanViewModelTest" 2>&1 | tail -5`
Expected: All tests PASS

- [ ] **Step 5: Run ktlint, fix if needed**

Run: `cd mobile && ./gradlew :app:ktlintFormat :app:ktlintCheck 2>&1 | tail -3`

- [ ] **Step 6: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/presentation/ble/BleScanViewModel.kt app/src/test/java/ru/skatelab/capture/presentation/ble/BleScanViewModelTest.kt
git commit -m "feat(android): auto-refresh SensorInfo on connect in BleScanViewModel"
```

---

### Task 8: BleScanScreen SensorInfo display

**Files:**

- Modify: `app/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt`

- [ ] **Step 1: Add SensorInfo import and display**

Add import at top:

```kotlin
import ru.skatelab.capture.domain.model.SensorInfo
```

In `BleScanScreen`, collect `sensorInfo`:

```kotlin
val sensorInfo by viewModel.sensorInfo.collectAsState()
```

Update `ScanDeviceRow` call to pass `sensorInfo`:

```kotlin
ScanDeviceRow(
    device = device,
    leftInfo = sensorInfo[SensorId.LEFT],
    rightInfo = sensorInfo[SensorId.RIGHT],
    leftConnected = ...,
    rightConnected = ...,
    onConnectLeft = ...,
    onConnectRight = ...,
    onFactoryResetLeft = ...,
    onFactoryResetRight = ...,
    onAccCalibrateLeft = ...,
    onAccCalibrateRight = ...,
)
```

Update `ScanDeviceRow` signature — add `leftInfo: SensorInfo?` and `rightInfo: SensorInfo?` params.

After the factory-reset/calibration buttons `Row`, add:

```kotlin
if (leftInfo != null) {
    SensorInfoRow(info = leftInfo, label = "Левый")
}
if (rightInfo != null) {
    SensorInfoRow(info = rightInfo, label = "Правый")
}
```

Add a new composable:

```kotlin
@Composable
private fun SensorInfoRow(
    info: SensorInfo,
    label: String,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            "$label: ${info.batteryPercent}% (${info.batteryMv}mV)",
            style = MaterialTheme.typography.labelSmall,
        )
        Text(
            "ID:${info.deviceId.takeLast(4)} FW:${info.firmwareVersion}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
```

- [ ] **Step 2: Compile to verify**

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Run ktlint, fix if needed**

Run: `cd mobile && ./gradlew :app:ktlintFormat :app:ktlintCheck 2>&1 | tail -3`

- [ ] **Step 4: Commit**

```bash
git add app/src/main/java/ru/skatelab/capture/presentation/ble/BleScanScreen.kt
git commit -m "feat(android): display SensorInfo (battery, ID, FW) on BleScanScreen"
```

---

## Wave 5: Final verification

### Task 9: Full build + all tests

- [ ] **Step 1: Run full unit test suite**

Run: `cd mobile && ./gradlew :app:testDebugUnitTest 2>&1 | tail -10`
Expected: All tests PASS

- [ ] **Step 2: Run ktlint check**

Run: `cd mobile && ./gradlew :app:ktlintCheck 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Run debug compilation**

Run: `cd mobile && ./gradlew :app:compileDebugKotlin 2>&1 | tail -3`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Final commit (if any ktlint/format fixes)**

Only if there were fixes:

```bash
git add -A
git commit -m "style(android): ktlint fixes for BLE feature expansion"
```
