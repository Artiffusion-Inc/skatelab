package ru.skatelab.capture.data.sync

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

@OptIn(ExperimentalCoroutinesApi::class)
class PeriodicTimeSyncTest {
    private lateinit var timeSyncManager: TimeSyncManager
    private lateinit var bleRepository: BleRepository
    private lateinit var appLogger: AppLogger
    private lateinit var periodicTimeSync: PeriodicTimeSync

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        timeSyncManager = TimeSyncManager(bleRepository)
        appLogger = mockk(relaxed = true)
        periodicTimeSync = PeriodicTimeSync(timeSyncManager, bleRepository, appLogger, clockNanos = { 1_000_000_000L })
    }

    @After
    fun tearDown() {
        periodicTimeSync.stop()
    }

    @Test
    fun `sync reads chip time for both sensors`() =
        runTest {
            coEvery { bleRepository.readChipTime(SensorId.LEFT) } returns Result.success(1000L)
            coEvery { bleRepository.readChipTime(SensorId.RIGHT) } returns Result.success(2000L)

            periodicTimeSync.sync(this)
            periodicTimeSync.awaitSync()

            coVerify(exactly = 1) { bleRepository.readChipTime(SensorId.LEFT) }
            coVerify(exactly = 1) { bleRepository.readChipTime(SensorId.RIGHT) }
        }

    @Test
    fun `successful sync calls updatePeriodicOffset`() =
        runTest {
            coEvery { bleRepository.readChipTime(SensorId.LEFT) } returns Result.success(5000L)
            coEvery { bleRepository.readChipTime(SensorId.RIGHT) } returns Result.success(6000L)

            periodicTimeSync.sync(this)
            periodicTimeSync.awaitSync()

            assertEquals(4_000_000_000L, timeSyncManager.getOffset(SensorId.LEFT))
            assertEquals(5_000_000_000L, timeSyncManager.getOffset(SensorId.RIGHT))
        }

    @Test
    fun `sync is one-shot — no periodic retries`() =
        runTest {
            coEvery { bleRepository.readChipTime(SensorId.LEFT) } returns Result.success(100L)
            coEvery { bleRepository.readChipTime(SensorId.RIGHT) } returns Result.success(200L)

            periodicTimeSync.sync(this)
            periodicTimeSync.awaitSync()

            // After awaitSync, no more reads should happen
            advanceTimeBy(60_000L)
            runCurrent()

            coVerify(exactly = 1) { bleRepository.readChipTime(SensorId.LEFT) }
            coVerify(exactly = 1) { bleRepository.readChipTime(SensorId.RIGHT) }
        }

    @Test
    fun `stop cancels pending sync`() =
        runTest {
            coEvery { bleRepository.readChipTime(any()) } returns Result.success(0L)

            periodicTimeSync.sync(this)
            runCurrent()
            periodicTimeSync.stop()

            // Each sensor read is called at most once
            coVerify(atMost = 1) { bleRepository.readChipTime(SensorId.LEFT) }
            coVerify(atMost = 1) { bleRepository.readChipTime(SensorId.RIGHT) }
        }

    @Test
    fun `stop when not started is no-op`() {
        periodicTimeSync.stop()
    }

    @Test
    fun `sync called twice restarts`() =
        runTest {
            coEvery { bleRepository.readChipTime(any()) } returns Result.success(0L)

            periodicTimeSync.sync(this)
            runCurrent()

            periodicTimeSync.sync(this)
            runCurrent()
            periodicTimeSync.stop()

            coVerify(exactly = 2) { bleRepository.readChipTime(SensorId.LEFT) }
            coVerify(exactly = 2) { bleRepository.readChipTime(SensorId.RIGHT) }
        }

    @Test
    fun `failed read logs warning and does not update offset`() =
        runTest {
            coEvery { bleRepository.readChipTime(SensorId.LEFT) } returns
                Result.failure(IllegalStateException("GATT error"))
            coEvery { bleRepository.readChipTime(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("GATT error"))

            periodicTimeSync.sync(this)
            periodicTimeSync.awaitSync()

            verify(exactly = 2) { appLogger.w("TimeSync", any()) }
            assertEquals(0L, timeSyncManager.getOffset(SensorId.LEFT))
            assertEquals(0L, timeSyncManager.getOffset(SensorId.RIGHT))
        }

    @Test
    fun `partial failure updates successful sensor only`() =
        runTest {
            coEvery { bleRepository.readChipTime(SensorId.LEFT) } returns
                Result.failure(IllegalStateException("BLE read error"))
            coEvery { bleRepository.readChipTime(SensorId.RIGHT) } returns Result.success(500L)

            periodicTimeSync.sync(this)
            periodicTimeSync.awaitSync()

            verify(exactly = 1) { appLogger.w("TimeSync", any()) }
            assert(timeSyncManager.getOffset(SensorId.RIGHT) != 0L)
            assertEquals(0L, timeSyncManager.getOffset(SensorId.LEFT))
        }

    @Test
    fun `awaitSync without sync is no-op`() =
        runTest {
            // Should complete immediately without error
            periodicTimeSync.awaitSync()
        }
}
