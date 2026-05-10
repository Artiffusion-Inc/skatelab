package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import kotlin.math.sqrt

class CalibrateSensorUseCaseTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var bleRepository: BleRepository
    private lateinit var appLogger: AppLogger
    private lateinit var useCase: CalibrateSensorUseCase

    private val imuSamplesFlow = MutableSharedFlow<Pair<SensorId, ImuSample>>(
        replay = 600,
        extraBufferCapacity = 0,
    )

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)

        every { bleRepository.imuSamples } returns imuSamplesFlow
        coEvery { bleRepository.startStreaming(any()) } returns Result.success(Unit)
        coEvery { bleRepository.stopStreaming(any()) } returns Result.success(Unit)

        useCase = CalibrateSensorUseCase(bleRepository, appLogger)
    }

    private fun stillSample(
        timestampNs: Long,
        quatW: Float = 1f,
        quatX: Float = 0f,
        quatY: Float = 0f,
        quatZ: Float = 0f,
    ) = ImuSample(
        timestampNs = timestampNs,
        accX = 0f, accY = 0f, accZ = 9.81f,
        gyroX = 0f, gyroY = 0f, gyroZ = 0f,
        quatW = quatW, quatX = quatX, quatY = quatY, quatZ = quatZ,
    )

    private fun movingSample(timestampNs: Long) = ImuSample(
        timestampNs = timestampNs,
        accX = 0f, accY = 0f, accZ = 9.81f,
        gyroX = 1.0f, gyroY = 1.0f, gyroZ = 1.0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )

    private fun warmupZeroSample(timestampNs: Long) = ImuSample(
        timestampNs = timestampNs,
        accX = 0f, accY = 0f, accZ = 0f,  // Below 1.0 m/s² threshold
        gyroX = 0f, gyroY = 0f, gyroZ = 0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )

    private fun CoroutineScope.launchCalibrationWithSamples(
        samples: List<Pair<SensorId, ImuSample>>,
    ): Pair<Job, Job> {
        val emitterJob = launch {
            delay(1L)
            for (sample in samples) {
                imuSamplesFlow.emit(sample)
                delay(1L)
            }
        }
        val calibrationJob = launch {
            useCase.invokeBoth()
        }
        return Pair(emitterJob, calibrationJob)
    }

    @Test
    fun invokeBoth_bothSensors_returnsBothCalibrations() = testScope.runTest {
        val samples = List(500) { i ->
            if (i % 2 == 0) SensorId.LEFT to stillSample(i.toLong())
            else SensorId.RIGHT to stillSample(i.toLong())
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.startStreaming(SensorId.LEFT) }
        coVerify { bleRepository.startStreaming(SensorId.RIGHT) }
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun invokeBoth_startStreamingFailure_returnsFailure() = testScope.runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns
            Result.failure(IllegalStateException("BLE connection lost"))

        val result = useCase.invokeBoth()

        assertTrue("Expected failure", result.isFailure)
        coVerify { bleRepository.startStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun invokeBoth_noStillSamples_returnsFailure() = testScope.runTest {
        val job = testScope.backgroundScope.launch {
            try {
                useCase.invokeBoth()
            } catch (_: kotlinx.coroutines.CancellationException) { }
        }

        advanceUntilIdle()

        repeat(10) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to movingSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to movingSample(i.toLong()))
        }

        advanceTimeBy(12_001L)
        advanceUntilIdle()

        assertTrue("Job should be completed", job.isCompleted)
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun invokeBoth_warmupZerosFiltered() = testScope.runTest {
        val samples = mutableListOf<Pair<SensorId, ImuSample>>()
        // Warm-up zeros first (should be discarded)
        repeat(10) { i ->
            samples.add(SensorId.LEFT to warmupZeroSample(i.toLong()))
            samples.add(SensorId.RIGHT to warmupZeroSample(i.toLong()))
        }
        // Then real still samples
        repeat(500) { i ->
            samples.add(SensorId.LEFT to stillSample((10 + i).toLong()))
            samples.add(SensorId.RIGHT to stillSample((10 + i).toLong()))
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun invokeBoth_partialResult_oneSensorStill() = testScope.runTest {
        val samples = mutableListOf<Pair<SensorId, ImuSample>>()
        // LEFT gets still samples, RIGHT gets only moving
        repeat(500) { i ->
            samples.add(SensorId.LEFT to stillSample(i.toLong()))
            samples.add(SensorId.RIGHT to movingSample(i.toLong()))
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun invokeBoth_stopsStreamingOnSuccess() = testScope.runTest {
        val samples = List(500) { i ->
            if (i % 2 == 0) SensorId.LEFT to stillSample(i.toLong())
            else SensorId.RIGHT to stillSample(i.toLong())
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun computeMeanQuaternion_identitySamples() {
        val samples = List(5) { i ->
            stillSample(i.toLong(), quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f)
        }
        val mean = invokeComputeMeanQuaternion(samples)
        assertArrayEquals(floatArrayOf(1f, 0f, 0f, 0f), mean, 0.001f)
    }

    @Test
    fun computeMeanQuaternion_hemisphereFlip() {
        val samples = listOf(
            stillSample(0L, quatW = 0.7071f, quatX = 0.7071f, quatY = 0f, quatZ = 0f),
            stillSample(1L, quatW = -0.7071f, quatX = -0.7071f, quatY = 0f, quatZ = 0f),
        )
        val mean = invokeComputeMeanQuaternion(samples)
        assertEquals(0.7071f, mean[0], 0.01f)
        assertEquals(0.7071f, mean[1], 0.01f)
        assertEquals(0.0f, mean[2], 0.01f)
        assertEquals(0.0f, mean[3], 0.01f)
    }

    @Test
    fun computeMeanQuaternion_normalizedOutput() {
        val samples = listOf(
            stillSample(0L, quatW = 2f, quatX = 0f, quatY = 0f, quatZ = 0f),
            stillSample(1L, quatW = 2f, quatX = 0f, quatY = 0f, quatZ = 0f),
        )
        val mean = invokeComputeMeanQuaternion(samples)
        val norm = sqrt((mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] + mean[3] * mean[3]).toDouble()).toFloat()
        assertEquals(1.0f, norm, 0.001f)
        assertEquals(1.0f, mean[0], 0.001f)
    }

    private fun invokeComputeMeanQuaternion(samples: List<ImuSample>): FloatArray {
        val method = CalibrateSensorUseCase::class.java.getDeclaredMethod(
            "computeMeanQuaternion", List::class.java
        )
        method.isAccessible = true
        return method.invoke(useCase, samples) as FloatArray
    }
}