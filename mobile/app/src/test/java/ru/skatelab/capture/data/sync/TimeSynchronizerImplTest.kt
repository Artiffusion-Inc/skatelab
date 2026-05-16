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
    fun `sync calls configureSensorTime when offset is zero (first sync)`() =
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
