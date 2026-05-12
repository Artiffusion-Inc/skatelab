package ru.skatelab.capture.domain.usecase

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
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
        private const val WARMUP_MS = 1_000L
        private const val WARMUP_MIN_ACC_MAGNITUDE = 1.0f
    }

    /**
     * Calibrate both sensors simultaneously from the same pose.
     * Assumes sensors are already streaming (preview handles streaming lifecycle).
     * Collects still samples in parallel and computes mean quaternions independently.
     * This ensures quatRef values refer to the same moment, which is required for
     * correct quatRef⁻¹ * q_sample correction.
     *
     * @param onProgress callback invoked with progress percentage (0..100)
     */
    suspend fun invokeBoth(onProgress: ((Int) -> Unit)? = null): Result<Map<SensorId, CalibrationData>> {
        return try {
            appLogger.i(TAG, "Collecting still samples from active streams")

            val leftSamples = mutableListOf<ImuSample>()
            val rightSamples = mutableListOf<ImuSample>()
            collectStillSamplesBoth(leftSamples, rightSamples, onProgress)

            appLogger.i(TAG, "Collected LEFT=${leftSamples.size}, RIGHT=${rightSamples.size} still samples")

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
            throw e
        } catch (e: Exception) {
            appLogger.e(TAG, "Parallel calibration failed: ${e.message}")
            Result.failure(e)
        }
    }

    private suspend fun collectStillSamplesBoth(
        leftSamples: MutableList<ImuSample>,
        rightSamples: MutableList<ImuSample>,
        onProgress: ((Int) -> Unit)?,
    ) {
        var leftReceived = 0
        var rightReceived = 0
        var elapsedMs = 0L

        coroutineScope {
            val collectJob = launch {
                val skipUntil = System.currentTimeMillis() + WARMUP_MS
                bleRepository.imuSamples.collect { (sensorId, sample) ->
                    if (System.currentTimeMillis() < skipUntil) return@collect
                    val accMag = sqrt(
                        (sample.accX * sample.accX +
                                sample.accY * sample.accY +
                                sample.accZ * sample.accZ).toDouble()
                    ).toFloat()
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
                }
            }

            withTimeout(COLLECTION_TIMEOUT_MS) {
                val progressStep = 100L
                var lastProgressReport = 0
                while (isActive) {
                    delay(progressStep)
                    elapsedMs += progressStep
                    if (elapsedMs >= COLLECTION_DURATION_MS) break
                    if (leftSamples.size >= MAX_STILL_SAMPLES && rightSamples.size >= MAX_STILL_SAMPLES) break
                    val progress = ((elapsedMs * 100) / COLLECTION_DURATION_MS).toInt().coerceIn(0, 99)
                    if (progress != lastProgressReport) {
                        lastProgressReport = progress
                        onProgress?.invoke(progress)
                    }
                }
            }
            collectJob.cancel()
            onProgress?.invoke(100)
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
