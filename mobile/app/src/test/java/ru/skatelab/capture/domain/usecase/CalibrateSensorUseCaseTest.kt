package ru.skatelab.capture.domain.usecase

import io.mockk.every
import io.mockk.mockk
import kotlin.math.sqrt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.yield
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.service.Logger

class CalibrateSensorUseCaseTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)
    private lateinit var bleRepository: BleRepository
    private lateinit var appLogger: Logger
    private lateinit var useCase: CalibrateSensorUseCase

    private val imuSamplesFlow =
        MutableSharedFlow<Pair<SensorId, ImuSample>>(
            extraBufferCapacity = 2048,
        )

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        bleRepository = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)

        every { bleRepository.imuSamples } returns imuSamplesFlow

        useCase = CalibrateSensorUseCase(bleRepository, appLogger)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
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

    private fun movingSample(timestampNs: Long) =
        ImuSample(
            timestampNs = timestampNs,
            accX = 0f, accY = 0f, accZ = 9.81f,
            gyroX = 10.0f, gyroY = 10.0f, gyroZ = 10.0f,
            quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
        )

    private suspend fun emitStillInterleaved(count: Int) {
        repeat(count) { i ->
            imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
            imuSamplesFlow.emit(SensorId.RIGHT to stillSample(i.toLong()))
            yield()
        }
    }

    @Test
    fun invokeBoth_bothSensors_returnsBothCalibrations() =
        testScope.runTest {
            val calibrationDeferred = async { useCase() }

            // Let collect coroutine subscribe to the flow
            runCurrent()

            // Advance past warmup period so samples are accepted
            advanceTimeBy(1_500L)
            runCurrent()

            // Emit still samples — warmedUp is now true
            launch { emitStillInterleaved(500) }
            runCurrent()

            // Advance past collection duration
            advanceTimeBy(10_000L)
            runCurrent()

            val result = calibrationDeferred.await()
            assertTrue("Expected success, got: ${result.exceptionOrNull()?.message}", result.isSuccess)
            val calMap = result.getOrThrow()
            assertTrue("LEFT should be calibrated", calMap.containsKey(SensorId.LEFT))
            assertTrue("RIGHT should be calibrated", calMap.containsKey(SensorId.RIGHT))
        }

    @Test
    fun invokeBoth_noStillSamples_returnsFailure() =
        testScope.runTest {
            val calibrationDeferred = async { useCase() }
            runCurrent()

            // Advance past warmup
            advanceTimeBy(1_500L)
            runCurrent()

            // Emit only moving samples — none will pass isStill check
            launch {
                repeat(20) { i ->
                    imuSamplesFlow.emit(SensorId.LEFT to movingSample(i.toLong()))
                    imuSamplesFlow.emit(SensorId.RIGHT to movingSample(i.toLong()))
                    yield()
                }
            }
            runCurrent()

            advanceTimeBy(12_000L)
            runCurrent()

            val result = calibrationDeferred.await()
            assertTrue("Expected failure", result.isFailure)
        }

    @Test
    fun invokeBoth_warmupSamplesFiltered() =
        testScope.runTest {
            val calibrationDeferred = async { useCase() }
            runCurrent()

            // Emit samples DURING warmup (warmedUp = false) — should be filtered
            launch {
                repeat(50) { i ->
                    imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
                    imuSamplesFlow.emit(SensorId.RIGHT to stillSample(i.toLong()))
                    yield()
                }
            }
            runCurrent()

            // Advance past warmup
            advanceTimeBy(1_500L)
            runCurrent()

            // Emit still samples AFTER warmup (warmedUp = true)
            launch { emitStillInterleaved(500) }
            runCurrent()

            // Advance past collection duration
            advanceTimeBy(10_000L)
            runCurrent()

            val result = calibrationDeferred.await()
            assertTrue("Expected success, got: ${result.exceptionOrNull()?.message}", result.isSuccess)
        }

    @Test
    fun invokeBoth_partialResult_oneSensorStill() =
        testScope.runTest {
            val calibrationDeferred = async { useCase() }
            runCurrent()

            // Advance past warmup
            advanceTimeBy(1_500L)
            runCurrent()

            launch {
                repeat(500) { i ->
                    imuSamplesFlow.emit(SensorId.LEFT to stillSample(i.toLong()))
                    imuSamplesFlow.emit(SensorId.RIGHT to movingSample(i.toLong()))
                    yield()
                }
            }
            runCurrent()

            advanceTimeBy(10_000L)
            runCurrent()

            val result = calibrationDeferred.await()
            assertTrue("Expected success, got: ${result.exceptionOrNull()?.message}", result.isSuccess)
            val calMap = result.getOrThrow()
            assertTrue(calMap.containsKey(SensorId.LEFT))
            assertTrue("RIGHT should not be calibrated with moving samples", !calMap.containsKey(SensorId.RIGHT))
        }

    @Test
    fun invokeBoth_progressCallback_invoked() =
        testScope.runTest {
            val progressValues = mutableListOf<Int>()
            val calibrationDeferred = async { useCase { progressValues.add(it) } }
            runCurrent()

            // Advance past warmup
            advanceTimeBy(1_500L)
            runCurrent()

            launch { emitStillInterleaved(500) }
            runCurrent()

            advanceTimeBy(10_000L)
            runCurrent()

            calibrationDeferred.await()
            assertTrue("Progress should have been reported", progressValues.isNotEmpty())
            assertEquals(100, progressValues.last())
        }

    @Test
    fun computeMeanQuaternion_identitySamples() {
        val samples =
            List(5) { i ->
                stillSample(i.toLong(), quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f)
            }
        val mean = invokeComputeMeanQuaternion(samples)
        assertArrayEquals(floatArrayOf(1f, 0f, 0f, 0f), mean, 0.001f)
    }

    @Test
    fun computeMeanQuaternion_hemisphereFlip() {
        val samples =
            listOf(
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
        val samples =
            listOf(
                stillSample(0L, quatW = 2f, quatX = 0f, quatY = 0f, quatZ = 0f),
                stillSample(1L, quatW = 2f, quatX = 0f, quatY = 0f, quatZ = 0f),
            )
        val mean = invokeComputeMeanQuaternion(samples)
        val norm = sqrt((mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] + mean[3] * mean[3]).toDouble()).toFloat()
        assertEquals(1.0f, norm, 0.001f)
        assertEquals(1.0f, mean[0], 0.001f)
    }

    @Test
    fun computeMeanQuaternion_clusteredQuaternions_returnsMarkleyMean() {
        val samples = listOf(
            stillSample(0L, quatW = 0.9998f, quatX = 0.01f, quatY = 0.005f, quatZ = 0.002f),
            stillSample(1L, quatW = 0.9999f, quatX = 0.008f, quatY = 0.006f, quatZ = 0.001f),
            stillSample(2L, quatW = 0.9997f, quatX = 0.012f, quatY = 0.004f, quatZ = 0.003f),
            stillSample(3L, quatW = 0.9998f, quatX = 0.009f, quatY = 0.007f, quatZ = 0.002f),
            stillSample(4L, quatW = 0.9999f, quatX = 0.011f, quatY = 0.003f, quatZ = 0.001f),
        )
        val mean = invokeComputeMeanQuaternion(samples)
        val meanNorm = sqrt((mean[0] * mean[0] + mean[1] * mean[1] + mean[2] * mean[2] + mean[3] * mean[3]).toDouble()).toFloat()
        assertEquals(1.0f, meanNorm, 0.01f)
        val dot = mean[0]
        assertTrue("Mean w component should be positive (dot=$dot)", dot > 0.9f)
    }

    @Test
    fun computeMeanQuaternion_hemisphereFlip_fixedReference() {
        val samples = listOf(
            stillSample(0L, quatW = 0.7071f, quatX = 0.7071f, quatY = 0f, quatZ = 0f),
            stillSample(1L, quatW = -0.7071f, quatX = -0.7071f, quatY = 0f, quatZ = 0f),
            stillSample(2L, quatW = 0.7071f, quatX = 0.7071f, quatY = 0f, quatZ = 0f),
            stillSample(3L, quatW = -0.7071f, quatX = -0.7071f, quatY = 0f, quatZ = 0f),
        )
        val mean = invokeComputeMeanQuaternion(samples)
        assertTrue("Mean w should be positive", mean[0] > 0f)
        assertTrue("Mean x should be positive", mean[1] > 0f)
        assertEquals(0f, mean[2], 0.01f)
        assertEquals(0f, mean[3], 0.01f)
    }

    @Test
    fun computeMeanQuaternion_singleQuaternion_returnsThatQuaternion() {
        val samples = listOf(
            stillSample(0L, quatW = 0.5f, quatX = 0.5f, quatY = 0.5f, quatZ = 0.5f),
        )
        val mean = invokeComputeMeanQuaternion(samples)
        assertArrayEquals(floatArrayOf(0.5f, 0.5f, 0.5f, 0.5f), mean, 0.01f)
    }

    @Test
    fun dominantEigenvector_rank1Matrix_returnsExpectedVector() {
        val n = 100f
        val qw = 0.5f; val qx = 0.5f; val qy = 0.5f; val qz = 0.5f
        val norm = sqrt((qw * qw + qx * qx + qy * qy + qz * qz).toDouble()).toFloat()
        val w = qw / norm; val x = qx / norm; val y = qy / norm; val z = qz / norm

        val m00 = n * w * w; val m01 = n * w * x; val m02 = n * w * y; val m03 = n * w * z
        val m11 = n * x * x; val m12 = n * x * y; val m13 = n * x * z
        val m22 = n * y * y; val m23 = n * y * z
        val m33 = n * z * z

        val result = invokeDominantEigenvector4x4(
            m00, m01, m02, m03,
            m01, m11, m12, m13,
            m02, m12, m22, m23,
            m03, m13, m23, m33,
            w, x, y, z,
        )
        val rNorm = sqrt((result[0] * result[0] + result[1] * result[1] + result[2] * result[2] + result[3] * result[3]).toDouble()).toFloat()
        assertEquals(1.0f, rNorm, 0.001f)
        val dot = result[0] * w + result[1] * x + result[2] * y + result[3] * z
        assertTrue("Eigenvector should align with input (dot=$dot)", dot > 0.99f)
    }

    private fun invokeDominantEigenvector4x4(
        m00: Float, m01: Float, m02: Float, m03: Float,
        m10: Float, m11: Float, m12: Float, m13: Float,
        m20: Float, m21: Float, m22: Float, m23: Float,
        m30: Float, m31: Float, m32: Float, m33: Float,
        initW: Float, initX: Float, initY: Float, initZ: Float,
    ): FloatArray {
        val method = CalibrateSensorUseCase::class.java.getDeclaredMethod(
            "dominantEigenvector4x4",
            Float::class.java, Float::class.java, Float::class.java, Float::class.java,
            Float::class.java, Float::class.java, Float::class.java, Float::class.java,
            Float::class.java, Float::class.java, Float::class.java, Float::class.java,
            Float::class.java, Float::class.java, Float::class.java, Float::class.java,
            Float::class.java, Float::class.java, Float::class.java, Float::class.java,
        )
        method.isAccessible = true
        return method.invoke(useCase, m00, m01, m02, m03, m10, m11, m12, m13, m20, m21, m22, m23, m30, m31, m32, m33, initW, initX, initY, initZ) as FloatArray
    }

    private fun invokeComputeMeanQuaternion(samples: List<ImuSample>): FloatArray {
        val method =
            CalibrateSensorUseCase::class.java.getDeclaredMethod(
                "computeMeanQuaternion",
                List::class.java,
            )
        method.isAccessible = true
        return method.invoke(useCase, samples) as FloatArray
    }
}