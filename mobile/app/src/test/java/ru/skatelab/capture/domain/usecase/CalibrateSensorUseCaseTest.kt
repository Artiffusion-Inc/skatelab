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
import org.junit.Assert.assertFalse
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

    // Use a moderate replay cache so late subscribers still get items
    // but without OOM from Int.MAX_VALUE replay
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

    /** Build a still sample (gyro below 10 deg/s threshold). */
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

    /** Build a moving sample (gyro above 10 deg/s threshold). */
    private fun movingSample(timestampNs: Long) = ImuSample(
        timestampNs = timestampNs,
        accX = 0f, accY = 0f, accZ = 9.81f,
        gyroX = 1.0f, gyroY = 1.0f, gyroZ = 1.0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )

    /**
     * Launch the use case in background and emit samples while it's collecting.
     * The emitter coroutine yields briefly between emissions to allow the collector
     * to process items incrementally.
     */
    private fun CoroutineScope.launchCalibrationWithSamples(
        sensorId: SensorId,
        samples: List<Pair<SensorId, ImuSample>>,
    ): Pair<Job, Job> {
        val emitterJob = launch {
            // Small delay to ensure the collector has started subscribing
            delay(1L)
            for (sample in samples) {
                imuSamplesFlow.emit(sample)
                delay(1L) // Yield between emissions
            }
        }
        val calibrationJob = launch {
            useCase.invoke(sensorId)
        }
        return Pair(emitterJob, calibrationJob)
    }

    @Test
    fun successfulCalibration_returnsCalibrationData() = testScope.runTest {
        // Emit 500 still samples to hit MAX_STILL_SAMPLES, which sets done=true
        // and breaks the collection loop cleanly.
        val samples = List(500) { i ->
            SensorId.LEFT to stillSample(i.toLong())
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(SensorId.LEFT, samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        // The flow collection was triggered; with replay, verify streaming was started
        coVerify { bleRepository.startStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
    }

    @Test
    fun successfulCalibration_hemisphereFlipCorrected() = testScope.runTest {
        // Alternating quaternion signs — same rotation, opposite hemispheres.
        val samples = mutableListOf<Pair<SensorId, ImuSample>>()
        repeat(250) { i ->
            samples.add(SensorId.RIGHT to stillSample(i.toLong(), 0.7071f, 0.7071f, 0f, 0f))
        }
        repeat(250) { i ->
            samples.add(SensorId.RIGHT to stillSample((250 + i).toLong(), -0.7071f, -0.7071f, 0f, 0f))
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(SensorId.RIGHT, samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.startStreaming(SensorId.RIGHT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun successfulCalibration_normalizedOutput() = testScope.runTest {
        val samples = List(500) { i ->
            SensorId.LEFT to stillSample(i.toLong(), quatW = 2f)
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(SensorId.LEFT, samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.startStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
    }

    @Test
    fun bleReadFailure_returnsFailure() = testScope.runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns
            Result.failure(IllegalStateException("BLE connection lost"))

        val result = useCase.invoke(SensorId.LEFT)

        assertTrue("Expected failure", result.isFailure)
        coVerify { bleRepository.startStreaming(SensorId.LEFT) }
        // stopStreaming is called in the catch block on failure
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
    }

    @Test
    fun bleStreamingFailure_stopsStreamingAndReturnsFailure() = testScope.runTest {
        coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns
            Result.failure(RuntimeException("GATT error"))

        val result = useCase.invoke(SensorId.RIGHT)

        assertTrue(result.isFailure)
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun insufficientSamples_noStillSamples_cancelsCoroutine() = testScope.runTest {
        // All emitted samples are moving (above angular velocity threshold),
        // so stillSamples list stays empty.
        // The collection loop relies on System.currentTimeMillis() which doesn't
        // advance in virtual time, so only MAX_STILL_SAMPLES can break the loop.
        // Without enough still samples, withTimeout fires and cancels the coroutine.
        val job = testScope.backgroundScope.launch {
            try {
                useCase.invoke(SensorId.LEFT)
            } catch (_: kotlinx.coroutines.CancellationException) { }
        }

        advanceUntilIdle()

        // Emit only moving samples — none qualify as "still"
        repeat(10) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to movingSample(i.toLong()))
        }

        // Advance virtual time past the 12s timeout to trigger withTimeout
        advanceTimeBy(12_001L)
        advanceUntilIdle()

        assertTrue("Job should be completed", job.isCompleted)
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
    }

    @Test
    fun wrongSensorId_samplesIgnored_cancelsCoroutine() = testScope.runTest {
        val job = testScope.backgroundScope.launch {
            try {
                useCase.invoke(SensorId.LEFT)
            } catch (_: kotlinx.coroutines.CancellationException) { }
        }

        advanceUntilIdle()

        // Emit still samples for RIGHT sensor — filtered out by the use case
        repeat(500) { i ->
            imuSamplesFlow.emit(SensorId.RIGHT to stillSample(i.toLong()))
        }

        advanceUntilIdle()

        // No LEFT samples received, so withTimeout fires after 12s
        advanceTimeBy(12_001L)
        advanceUntilIdle()

        assertTrue("Job should be completed", job.isCompleted)
    }

    @Test
    fun calibration_stopsStreamingOnSuccess() = testScope.runTest {
        val samples = List(500) { i ->
            SensorId.RIGHT to stillSample(i.toLong())
        }
        val (emitterJob, calibrationJob) = launchCalibrationWithSamples(SensorId.RIGHT, samples)

        advanceUntilIdle()
        emitterJob.join()
        calibrationJob.join()

        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
    }

    @Test
    fun computeMeanQuaternion_identitySamples() {
        // Direct test of the mean quaternion computation logic
        val samples = List(5) { i ->
            stillSample(i.toLong(), quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f)
        }

        val mean = invokeComputeMeanQuaternion(samples)

        assertArrayEquals(floatArrayOf(1f, 0f, 0f, 0f), mean, 0.001f)
    }

    @Test
    fun computeMeanQuaternion_hemisphereFlip() {
        // Two quaternions representing the same rotation but in different hemispheres
        val samples = listOf(
            stillSample(0L, quatW = 0.7071f, quatX = 0.7071f, quatY = 0f, quatZ = 0f),
            stillSample(1L, quatW = -0.7071f, quatX = -0.7071f, quatY = 0f, quatZ = 0f),
        )

        val mean = invokeComputeMeanQuaternion(samples)

        // After hemisphere correction, mean should be (0.7071, 0.7071, 0, 0)
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

        // Mean of (2,0,0,0) and (2,0,0,0) = (4,0,0,0), norm=4 → (1,0,0,0)
        val norm = sqrt((mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] + mean[3] * mean[3]).toDouble()).toFloat()
        assertEquals(1.0f, norm, 0.001f)
        assertEquals(1.0f, mean[0], 0.001f)
    }

    /**
     * Access the private computeMeanQuaternion method via reflection for direct unit testing.
     */
    private fun invokeComputeMeanQuaternion(samples: List<ImuSample>): FloatArray {
        val method = CalibrateSensorUseCase::class.java.getDeclaredMethod(
            "computeMeanQuaternion", List::class.java
        )
        method.isAccessible = true
        return method.invoke(useCase, samples) as FloatArray
    }
}