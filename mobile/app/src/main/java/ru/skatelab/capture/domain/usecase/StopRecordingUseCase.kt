package ru.skatelab.capture.domain.usecase

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import javax.inject.Inject

class StopRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
) {
    data class StopResult(
        val actualFps: Int,
        val fpsVerified: Boolean,
    )

    /**
     * Stop recording with per-step error handling.
     * All cleanup steps always execute — a failure in one step
     * does not prevent other cleanup from running.
     * BLE stop for LEFT/RIGHT runs in parallel.
     */
    suspend operator fun invoke(): Result<StopResult> {
        val errors = mutableListOf<Throwable>()
        var stopResult = CameraRepository.RecordingStopResult(actualFps = 0, fpsVerified = false)

        try {
            withContext(Dispatchers.Main) {
                stopResult = cameraRepository.stopRecording().getOrDefault(stopResult)
            }
        } catch (e: Exception) {
            errors.add(e)
        }

        try {
            coroutineScope {
                withContext(Dispatchers.IO) {
                    val left = async { bleRepository.stopStreaming(SensorId.LEFT) }
                    val right = async { bleRepository.stopStreaming(SensorId.RIGHT) }
                    left.await().getOrDefault(Unit)
                    right.await().getOrDefault(Unit)
                }
            }
        } catch (e: Exception) {
            errors.add(e)
        }

        try {
            withContext(Dispatchers.Main) {
                cameraRepository.release()
            }
        } catch (e: Exception) {
            errors.add(e)
        }

        val result = StopResult(
            actualFps = stopResult.actualFps,
            fpsVerified = stopResult.fpsVerified,
        )
        return if (errors.isEmpty()) Result.success(result) else Result.failure(errors.first())
    }
}