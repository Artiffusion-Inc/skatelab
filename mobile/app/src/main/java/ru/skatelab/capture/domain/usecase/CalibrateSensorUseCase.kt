package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import kotlin.math.sqrt
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.service.Logger

class CalibrateSensorUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val appLogger: Logger,
    ) {
        companion object {
            private const val TAG = "CalibrateSensorUC"
            private const val COLLECTION_TIMEOUT_MS = 12_000L
            private const val COLLECTION_DURATION_MS = 10_000L
            private const val ANGULAR_VELOCITY_THRESHOLD_DEG_S = 5.0
            private const val ACC_MAG_MIN = 9.3
            private const val ACC_MAG_MAX = 10.3
            private const val MIN_STILL_SAMPLES = 50
            private const val WARMUP_MS = 1_000L
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
        suspend operator fun invoke(onProgress: ((Int) -> Unit)? = null): Result<Map<SensorId, CalibrationData>> {
            return try {
                appLogger.i(TAG, "Collecting still samples from active streams")

                val leftSamples = mutableListOf<ImuSample>()
                val rightSamples = mutableListOf<ImuSample>()
                collectStillSamplesBoth(leftSamples, rightSamples, onProgress)

                appLogger.i(TAG, "Collected LEFT=${leftSamples.size}, RIGHT=${rightSamples.size} still samples")

                if (leftSamples.size < MIN_STILL_SAMPLES || rightSamples.size < MIN_STILL_SAMPLES) {
                    return Result.failure(
                        IllegalStateException(
                            "Insufficient still samples: left=${leftSamples.size}, right=${rightSamples.size}. " +
                                "Hold sensors still for at least 5 seconds.",
                        ),
                    )
                }

                val result = mutableMapOf<SensorId, CalibrationData>()
                result[SensorId.LEFT] =
                    CalibrationData(
                        quatRef = computeMeanQuaternion(leftSamples),
                        calibratedAt = System.currentTimeMillis(),
                    )
                result[SensorId.RIGHT] =
                    CalibrationData(
                        quatRef = computeMeanQuaternion(rightSamples),
                        calibratedAt = System.currentTimeMillis(),
                    )
                Result.success(result)
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
                var warmedUp = false

                launch {
                    delay(WARMUP_MS)
                    warmedUp = true
                    appLogger.i(TAG, "Warmup complete, collecting still samples")
                }

                val collectJob =
                    launch {
                        var debugCount = 0
                        bleRepository.imuSamples.collect { (sensorId, sample) ->
                            debugCount++
                            if (debugCount <= 10 || debugCount % 100 == 0) {
                                val accMag =
                                    sqrt((sample.accX * sample.accX + sample.accY * sample.accY + sample.accZ * sample.accZ).toDouble())
                                val gyroMag =
                                    sqrt(
                                        (
                                            sample.gyroX * sample.gyroX +
                                                sample.gyroY * sample.gyroY +
                                                sample.gyroZ * sample.gyroZ
                                        ).toDouble(),
                                    )
                                appLogger.i(
                                    TAG,
                                    "collect #$debugCount: sensorId=$sensorId, accMag=$accMag, gyroMag=$gyroMag",
                                )
                            }
                            if (!warmedUp) return@collect
                            val gyroMagDegS =
                                sqrt(
                                    (
                                        sample.gyroX * sample.gyroX +
                                            sample.gyroY * sample.gyroY +
                                            sample.gyroZ * sample.gyroZ
                                    ).toDouble(),
                                )
                            val accMag =
                                sqrt(
                                    (
                                        sample.accX * sample.accX +
                                            sample.accY * sample.accY +
                                            sample.accZ * sample.accZ
                                    ).toDouble(),
                                )
                            val isStill =
                                gyroMagDegS <= ANGULAR_VELOCITY_THRESHOLD_DEG_S &&
                                    accMag >= ACC_MAG_MIN && accMag <= ACC_MAG_MAX
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

            appLogger.i(
                TAG,
                "Total received: LEFT=$leftReceived, RIGHT=$rightReceived; still: LEFT=${leftSamples.size}, RIGHT=${rightSamples.size}",
            )
        }

        private fun computeMeanQuaternion(samples: List<ImuSample>): FloatArray {
            val refW = samples.first().quatW
            val refX = samples.first().quatX
            val refY = samples.first().quatY
            val refZ = samples.first().quatZ

            var m00 = 0f; var m01 = 0f; var m02 = 0f; var m03 = 0f
            var m11 = 0f; var m12 = 0f; var m13 = 0f
            var m22 = 0f; var m23 = 0f
            var m33 = 0f

            for (sample in samples) {
                var qW = sample.quatW
                var qX = sample.quatX
                var qY = sample.quatY
                var qZ = sample.quatZ

                if (qW * refW + qX * refX + qY * refY + qZ * refZ < 0f) {
                    qW = -qW; qX = -qX; qY = -qY; qZ = -qZ
                }

                m00 += qW * qW; m01 += qW * qX; m02 += qW * qY; m03 += qW * qZ
                m11 += qX * qX; m12 += qX * qY; m13 += qX * qZ
                m22 += qY * qY; m23 += qY * qZ
                m33 += qZ * qZ
            }

            val m10 = m01; val m20 = m02; val m21 = m12; val m30 = m03; val m31 = m13; val m32 = m23

            return dominantEigenvector4x4(
                m00, m01, m02, m03,
                m10, m11, m12, m13,
                m20, m21, m22, m23,
                m30, m31, m32, m33,
                refW, refX, refY, refZ,
            )
        }

        private fun dominantEigenvector4x4(
            m00: Float,
            m01: Float,
            m02: Float,
            m03: Float,
            m10: Float,
            m11: Float,
            m12: Float,
            m13: Float,
            m20: Float,
            m21: Float,
            m22: Float,
            m23: Float,
            m30: Float,
            m31: Float,
            m32: Float,
            m33: Float,
            initW: Float,
            initX: Float,
            initY: Float,
            initZ: Float,
        ): FloatArray {
            var w = initW; var x = initX; var y = initY; var z = initZ
            for (i in 0 until 20) {
                val nw = m00 * w + m01 * x + m02 * y + m03 * z
                val nx = m10 * w + m11 * x + m12 * y + m13 * z
                val ny = m20 * w + m21 * x + m22 * y + m23 * z
                val nz = m30 * w + m31 * x + m32 * y + m33 * z
                val norm = sqrt(nw * nw + nx * nx + ny * ny + nz * nz)
                if (norm < 1e-10f) break
                w = nw / norm; x = nx / norm; y = ny / norm; z = nz / norm
            }
            return floatArrayOf(w, x, y, z)
        }
    }
