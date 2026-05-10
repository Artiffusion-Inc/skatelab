package ru.skatelab.capture.data.recording

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import java.io.File

@OptIn(ExperimentalCoroutinesApi::class)
class ImuCollectorTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var bleRepository: BleRepository
    private lateinit var appLogger: AppLogger
    private lateinit var collector: ImuCollector

    // replay=1 so late subscribers get the latest emission
    private val imuSamplesFlow = MutableSharedFlow<Pair<SensorId, ImuSample>>(
        extraBufferCapacity = 64,
    )
    private val reconnectEventsFlow = MutableSharedFlow<SensorId>(
        extraBufferCapacity = 16,
    )
    private val connectionStateFlow = MutableStateFlow(
        mapOf(SensorId.LEFT to BleRepository.ConnectionState.CONNECTED),
    )

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)

        every { bleRepository.imuSamples } returns imuSamplesFlow
        every { bleRepository.reconnectEvents } returns reconnectEventsFlow
        every { bleRepository.connectionState } returns connectionStateFlow
        coEvery { bleRepository.startStreaming(any()) } returns Result.success(Unit)

        collector = ImuCollector(bleRepository, appLogger, testDispatcher)
    }

    private fun sample(timestampNs: Long) = ImuSample(
        timestampNs = timestampNs,
        accX = 0.1f, accY = 0.2f, accZ = 9.8f,
        gyroX = 0f, gyroY = 0f, gyroZ = 0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )

    @Test
    fun start_opensWritersAndCollectsSamples() = testScope.runTest {
        val leftFile = File.createTempFile("imu_left", ".binpb")
        val rightFile = File.createTempFile("imu_right", ".binpb")
        leftFile.deleteOnExit()
        rightFile.deleteOnExit()

        collector.start(testScope, mapOf(SensorId.LEFT to leftFile, SensorId.RIGHT to rightFile))
        // Let the collect coroutine start and subscribe to the flow
        advanceUntilIdle()

        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(1_000_000L))
        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(2_000_000L))
        imuSamplesFlow.tryEmit(SensorId.RIGHT to sample(1_000_000L))
        advanceUntilIdle()

        val counts = collector.stop()
        assertEquals(2, counts[SensorId.LEFT])
        assertEquals(1, counts[SensorId.RIGHT])
    }

    @Test
    fun stop_closesWritersAndReturnsCounts() = testScope.runTest {
        val leftFile = File.createTempFile("imu_left_stop", ".binpb")
        leftFile.deleteOnExit()

        collector.start(testScope, mapOf(SensorId.LEFT to leftFile))
        advanceUntilIdle()

        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(5_000_000L))
        advanceUntilIdle()

        val counts = collector.stop()
        assertEquals(1, counts[SensorId.LEFT])

        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(6_000_000L))
        advanceUntilIdle()

        val counts2 = collector.stop()
        assertEquals(0, counts2.size)
    }

    @Test
    fun reconnectEvent_triggersGapInsertionOnNextSample() = testScope.runTest {
        val leftFile = File.createTempFile("imu_left_reconnect", ".binpb")
        leftFile.deleteOnExit()

        collector.start(testScope, mapOf(SensorId.LEFT to leftFile))
        advanceUntilIdle()

        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(10_000_000L))
        advanceUntilIdle()

        reconnectEventsFlow.tryEmit(SensorId.LEFT)
        advanceUntilIdle()

        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(50_000_000L))
        advanceUntilIdle()

        verify { appLogger.w("ImuCollector", match { it.contains("BLE reconnect gap") }) }
        verify { appLogger.i("ImuCollector", match { it.contains("IMUGap written") }) }

        collector.stop()
    }

    @Test
    fun start_ignoresUnmappedSensorId() = testScope.runTest {
        val leftFile = File.createTempFile("imu_left_filter", ".binpb")
        leftFile.deleteOnExit()

        collector.start(testScope, mapOf(SensorId.LEFT to leftFile))
        advanceUntilIdle()

        imuSamplesFlow.tryEmit(SensorId.RIGHT to sample(1_000_000L))
        imuSamplesFlow.tryEmit(SensorId.LEFT to sample(1_000_000L))
        advanceUntilIdle()

        val counts = collector.stop()
        assertEquals(1, counts[SensorId.LEFT])
        assertEquals(null, counts[SensorId.RIGHT])
    }
}
