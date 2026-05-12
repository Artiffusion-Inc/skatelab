package ru.skatelab.capture.domain.usecase

import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.test.UnconfinedTestDispatcher
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

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var bleRepository: BleRepository
    private lateinit var appLogger: AppLogger
    private lateinit var useCase: CalibrateSensorUseCase

    private val imuSamplesFlow = MutableSharedFlow<Pair<SensorId, ImuSample>>(
        replay = 0,
        extraBufferCapacity = 1024,
    )

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)

        every { bleRepository.imuSamples } returns imuSamplesFlow

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
        gyroX = 10.0f, gyroY = 10.0f, gyroZ = 10.0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )

    private fun warmupZeroSample(timestampNs: Long) = ImuSample(
        timestampNs = timestampNs,
        accX = 0f, accY = 0f, accZ = 0f,
        gyroX = 0f, gyroY = 0f, gyroZ = 0f,
        quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
    )

    @Test
    fun invokeBoth_bothSensors_returnsBothCalibrations() = runTest(testDispatcher) {
        val calibrationDeferred = async { useCase.invokeBoth() }

        // UnconfinedTestDispatcher dispatches immediately, so collector starts at once.
        // Emit samples synchronously — they go into SharedFlow buffer.
        repeat(500) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to stillSample(i.toLong()))
        }

        // Advance past collection duration so the while-loop's delay completes
        advanceTimeBy(11_000L)
        advanceUntilIdle()

        val result = calibrationDeferred.await()
        assertTrue("Expected success, got: ${result.exceptionOrNull()?.message}", result.isSuccess)
        val calMap = result.getOrThrow()
        assertTrue("LEFT should be calibrated", calMap.containsKey(SensorId.LEFT))
        assertTrue("RIGHT should be calibrated", calMap.containsKey(SensorId.RIGHT))
    }

    @Test
    fun invokeBoth_noStillSamples_returnsFailure() = runTest(testDispatcher) {
        val calibrationDeferred = async { useCase.invokeBoth() }

        // Emit only moving samples (filtered by gyro threshold)
        repeat(20) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to movingSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to movingSample(i.toLong()))
        }

        // Advance past timeout
        advanceTimeBy(13_000L)
        advanceUntilIdle()

        val result = calibrationDeferred.await()
        assertTrue("Expected failure", result.isFailure)
    }

    @Test
    fun invokeBoth_warmupZerosFiltered() = runTest(testDispatcher) {
        val calibrationDeferred = async { useCase.invokeBoth() }

        // Warm-up zeros (filtered by acc magnitude check)
        repeat(10) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to warmupZeroSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to warmupZeroSample(i.toLong()))
        }
        // Real still samples
        repeat(500) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to stillSample((10 + i).toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to stillSample((10 + i).toLong()))
        }

        advanceTimeBy(11_000L)
        advanceUntilIdle()

        val result = calibrationDeferred.await()
        assertTrue("Expected success, got: ${result.exceptionOrNull()?.message}", result.isSuccess)
        val calMap = result.getOrThrow()
        assertTrue(calMap.containsKey(SensorId.LEFT))
        assertTrue(calMap.containsKey(SensorId.RIGHT))
    }

    @Test
    fun invokeBoth_partialResult_oneSensorStill() = runTest(testDispatcher) {
        val calibrationDeferred = async { useCase.invokeBoth() }

        repeat(500) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to movingSample(i.toLong()))
        }

        advanceTimeBy(11_000L)
        advanceUntilIdle()

        val result = calibrationDeferred.await()
        assertTrue("Expected success, got: ${result.exceptionOrNull()?.message}", result.isSuccess)
        val calMap = result.getOrThrow()
        assertTrue(calMap.containsKey(SensorId.LEFT))
        assertTrue("RIGHT should not be calibrated with moving samples", !calMap.containsKey(SensorId.RIGHT))
    }

    @Test
    fun invokeBoth_progressCallback_invoked() = runTest(testDispatcher) {
        val progressValues = mutableListOf<Int>()
        val calibrationDeferred = async { useCase.invokeBoth { progressValues.add(it) } }

        repeat(500) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to stillSample(i.toLong()))
        }

        advanceTimeBy(11_000L)
        advanceUntilIdle()

        calibrationDeferred.await()
        assertTrue("Progress should have been reported", progressValues.isNotEmpty())
        assertEquals(100, progressValues.last())
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