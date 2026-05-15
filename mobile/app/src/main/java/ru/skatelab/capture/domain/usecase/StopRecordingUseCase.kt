package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository

class StopRecordingUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val cameraRepository: CameraRepository,
    ) {
        data class StopResult(
            val actualFps: Int,
            val fpsVerified: Boolean,
        )

        suspend operator fun invoke(): Result<StopResult> {
            val errors = mutableListOf<Throwable>()
            var stopResult = StopResult(actualFps = 0, fpsVerified = false)

            try {
                coroutineScope {
                    val cameraDeferred =
                        async(Dispatchers.IO) {
                            cameraRepository.stopRecording().getOrDefault(
                                CameraRepository.RecordingStopResult(actualFps = 0, fpsVerified = false),
                            )
                        }
                    val leftDeferred =
                        async(Dispatchers.IO) {
                            bleRepository.stopStreaming(SensorId.LEFT).getOrDefault(Unit)
                        }
                    val rightDeferred =
                        async(Dispatchers.IO) {
                            bleRepository.stopStreaming(SensorId.RIGHT).getOrDefault(Unit)
                        }
                    val cameraStop = cameraDeferred.await()
                    stopResult = StopResult(actualFps = cameraStop.actualFps, fpsVerified = cameraStop.fpsVerified)
                    leftDeferred.await()
                    rightDeferred.await()
                }
            } catch (e: Exception) {
                errors.add(e)
            }

            return if (errors.isEmpty()) Result.success(stopResult) else Result.failure(errors.first())
        }
    }