package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
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
            val firstFrameNs: Long,
            val actualWidth: Int = 0,
            val actualHeight: Int = 0,
        )

        suspend operator fun invoke(): Result<StopResult> {
            val cameraResult = cameraRepository.stopRecording()
            if (cameraResult.isFailure) {
                return Result.failure(cameraResult.exceptionOrNull()!!)
            }

            val stopResult = cameraResult.getOrThrow()
            bleRepository.stopStreaming(SensorId.LEFT)
            bleRepository.stopStreaming(SensorId.RIGHT)
            cameraRepository.release()

            return Result.success(
                StopResult(
                    actualFps = stopResult.actualFps,
                    fpsVerified = stopResult.fpsVerified,
                    firstFrameNs = stopResult.firstFrameNs,
                    actualWidth = stopResult.actualWidth,
                    actualHeight = stopResult.actualHeight,
                ),
            )
        }
    }
