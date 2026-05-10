package ru.skatelab.capture.domain.usecase

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import javax.inject.Inject
import kotlin.math.sqrt

class CalibrateSensorUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val appLogger: AppLogger,
) {
    companion object {
        private const val TAG = "CalibrateSensorUC"
        private const val COLLECTION_TIMEOUT_MS = 12_000L
        private const val COLLECTION_DURATION_MS = 10_000L
        private const val MAX_STILL_SAMPLES = 500
        private const val ANGULAR_VELOCITY_THRESHOLD_DEG_S = 10.0
        private const val WARMUP_MIN_ACC_MAGNITUDE = 1.0f
    }

    /**
     * Calibrate both sensors simultaneously from the same pose.
     * Both sensors stream at the same time, still samples are collected in parallel,
     * and mean quaternions are computed independently. This ensures quatRef values
     * refer to the same moment, which is required for correct quatRef⁻¹ * q_sample correction.
     */
    suspend fun invokeBoth(): Result<Map<SensorId, CalibrationData>> {
        return try {
            coroutineScope {
                val startLeft = async { bleRepository.startStreaming(SensorId.LEFT) }
                val startRight = async { bleRepository.startStreaming(SensorId.RIGHT) }
                val leftResult = startLeft.await()
                val rightResult = startRight.await()
                if (leftResult.isFailure) throw leftResult.exceptionOrNull()!!
                if (rightResult.isFailure) throw rightResult.exceptionOrNull()!!
            }
            appLogger.i(TAG, "Both sensors streaming, collecting still samples simultaneously")

            val leftSamples = mutableListOf<ImuSample>()
            val rightSamples = mutableListOf<ImuSample>()
            collectStillSamplesBoth(leftSamples, rightSamples)

            appLogger.i(TAG, "Collected LEFT=${leftSamples.size}, RIGHT=${rightSamples.size} still samples")

            // Stop both — always execute even if one fails
            val stopErrors = mutableListOf<Throwable>()
            bleRepository.stopStreaming(SensorId.LEFT)
                .onFailure { stopErrors.add(it) }
            bleRepository.stopStreaming(SensorId.RIGHT)
                .onFailure { stopErrors.add(it) }
            if (stopErrors.isNotEmpty()) {
                appLogger.w(TAG, "Stop streaming errors: ${stopErrors.map { it.message }}")
            }

            val result = mutableMapOf<SensorId, CalibrationData>()
            if (leftSamples.isNotEmpty()) {
                result[SensorId.LEFT] = CalibrationData(
                    quatRef = computeMeanQuaternion(leftSamples),
                    calibratedAt = System.currentTimeMillis(),
                )
            } else {
                appLogger.w(TAG, "No still samples for LEFT")
            }
            if (rightSamples.isNotEmpty()) {
                result[SensorId.RIGHT] = CalibrationData(
                    quatRef = computeMeanQuaternion(rightSamples),
                    calibratedAt = System.currentTimeMillis(),
                )
            } else {
                appLogger.w(TAG, "No still samples for RIGHT")
            }

            if (result.isEmpty()) {
                Result.failure(IllegalStateException("No still samples collected for either sensor"))
            } else {
                Result.success(result)
            }
        } catch (e: CancellationException) {
            bleRepository.stopStreaming(SensorId.LEFT)
            bleRepository.stopStreaming(SensorId.RIGHT)
            throw e
        } catch (e: Exception) {
            appLogger.e(TAG, "Parallel calibration failed: ${e.message}")
            bleRepository.stopStreaming(SensorId.LEFT)
            bleRepository.stopStreaming(SensorId.RIGHT)
            Result.failure(e)
        }
    }

    private suspend fun collectStillSamplesBoth(
        leftSamples: MutableList<ImuSample>,
        rightSamples: MutableList<ImuSample>,
    ) {
        val startTime = System.currentTimeMillis()
        var done = false
        var leftReceived = 0
        var rightReceived = 0

        coroutineScope {
            val collectJob = launch {
                bleRepository.imuSamples.collect { (sensorId, sample) ->
                    if (done) return@collect
                    val accMag = sqrt(
                        (sample.accX * sample.accX +
                                sample.accY * sample.accY +
                                sample.accZ * sample.accZ).toDouble()
                    ).toFloat()
                    // Discard WT901 warm-up zeros: sensor sends ~0 acc/gyro for ~0.5-1 s after streaming starts.
                    // Threshold matches ImuCollector.kt.
                    if (accMag < WARMUP_MIN_ACC_MAGNITUDE) return@collect
                    val gyroMagDegS = sqrt(
                        (sample.gyroX * sample.gyroX +
                                sample.gyroY * sample.gyroY +
                                sample.gyroZ * sample.gyroZ).toDouble()
                    )
                    val isStill = gyroMagDegS <= ANGULAR_VELOCITY_THRESHOLD_DEG_S
                    when (sensorId) {
                        SensorId.LEFT -> {
                            leftReceived++
                            if (isStill) leftSamples.add(sample)
                        }
                        SensorId.RIGHT -> {
                            rightReceived++
                            if (isStill) rightSamples.add(sample)
                        }
                    }
                    if (System.currentTimeMillis() - startTime >= COLLECTION_DURATION_MS ||
                        (leftSamples.size >= MAX_STILL_SAMPLES && rightSamples.size >= MAX_STILL_SAMPLES)
                    ) {
                        done = true
                    }
                }
            }

            withTimeout(COLLECTION_TIMEOUT_MS) {
                while (!done) {
                    delay(100L)
                }
            }
            collectJob.cancel()
        }

        appLogger.i(TAG, "Total received: LEFT=$leftReceived, RIGHT=$rightReceived; still: LEFT=${leftSamples.size}, RIGHT=${rightSamples.size}")
    }

    private fun computeMeanQuaternion(samples: List<ImuSample>): FloatArray {
        var refW = samples.first().quatW
        var refX = samples.first().quatX
        var refY = samples.first().quatY
        var refZ = samples.first().quatZ

        var sumW = 0f
        var sumX = 0f
        var sumY = 0f
        var sumZ = 0f
        var count = 0

        for (sample in samples) {
            var qW = sample.quatW
            var qX = sample.quatX
            var qY = sample.quatY
            var qZ = sample.quatZ

            // Hemisphere consistency: flip if dot(q_i, q_ref) < 0
            val dot = qW * refW + qX * refX + qY * refY + qZ * refZ
            if (dot < 0f) {
                qW = -qW
                qX = -qX
                qY = -qY
                qZ = -qZ
            }

            sumW += qW
            sumX += qX
            sumY += qY
            sumZ += qZ
            count++

            // Update reference to running mean for next iteration
            refW = sumW / count
            refX = sumX / count
            refY = sumY / count
            refZ = sumZ / count
        }

        // Normalize
        val norm = sqrt((sumW * sumW + sumX * sumX + sumY * sumY + sumZ * sumZ).toDouble()).toFloat()
        return floatArrayOf(sumW / norm, sumX / norm, sumY / norm, sumZ / norm)
    }
}
