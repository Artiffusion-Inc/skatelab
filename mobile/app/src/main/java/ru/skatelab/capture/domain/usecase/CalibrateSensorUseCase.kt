package ru.skatelab.capture.domain.usecase

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import javax.inject.Inject
import kotlin.math.sqrt

class CalibrateSensorUseCase @Inject constructor(
    private val bleRepository: BleRepository,
) {
    companion object {
        private const val COLLECTION_TIMEOUT_MS = 12_000L
        private const val COLLECTION_DURATION_MS = 10_000L
        private const val MAX_STILL_SAMPLES = 500
        private const val ANGULAR_VELOCITY_THRESHOLD_DEG_S = 5.0
        private const val DEG_TO_RAD = Math.PI / 180.0
    }

    suspend fun invoke(sensorId: SensorId): Result<CalibrationData> {
        return try {
            val samples = collectStillSamples(sensorId)

            if (samples.isEmpty()) {
                Result.failure(IllegalStateException("No still samples collected for $sensorId"))
            } else {
                val meanQ = computeMeanQuaternion(samples)
                Result.success(
                    CalibrationData(
                        quatRef = meanQ,
                        calibratedAt = System.currentTimeMillis(),
                    )
                )
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private suspend fun collectStillSamples(sensorId: SensorId): List<ImuSample> {
        val stillSamples = mutableListOf<ImuSample>()
        val startTime = System.currentTimeMillis()
        var done = false

        coroutineScope {
            val collectJob = launch {
                bleRepository.imuSamples
                    .filter { (id, _) -> id == sensorId }
                    .collect { (_, sample) ->
                        if (done) return@collect
                        val gyroRad = sqrt(
                            (sample.gyroX * sample.gyroX +
                                    sample.gyroY * sample.gyroY +
                                    sample.gyroZ * sample.gyroZ).toDouble()
                        )
                        val gyroDeg = gyroRad / DEG_TO_RAD
                        if (gyroDeg <= ANGULAR_VELOCITY_THRESHOLD_DEG_S) {
                            stillSamples.add(sample)
                        }
                        if (System.currentTimeMillis() - startTime >= COLLECTION_DURATION_MS ||
                            stillSamples.size >= MAX_STILL_SAMPLES
                        ) {
                            done = true
                        }
                    }
            }

            // Wait for collection duration, then cancel the collector
            withTimeout(COLLECTION_TIMEOUT_MS) {
                while (!done) {
                    delay(100L)
                }
            }
            collectJob.cancel()
        }

        return stillSamples.toList()
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
