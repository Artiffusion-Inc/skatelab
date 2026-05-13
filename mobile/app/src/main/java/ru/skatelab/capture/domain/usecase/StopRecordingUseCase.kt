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
     * Camera stop + BLE stop for LEFT/RIGHT run in parallel.
     */
    suspend operator fun invoke(): Result<StopResult> {
        val errors = mutableListOf<Throwable>()
        var stopResult = CameraRepository.RecordingStopResult(actualFps = 0, fpsVerified = false)

        // Camera stop + BLE stop in parallel — they're independent
        try {
            coroutineScope {
                val cameraDeferred = async(Dispatchers.Main) {
                    cameraRepository.stopRecording().getOrDefault(stopResult)
                }
                val leftDeferred = async(Dispatchers.IO) {
                    bleRepository.stopStreaming(SensorId.LEFT).getOrDefault(Unit)
                }
                val rightDeferred = async(Dispatchers.IO) {
                    bleRepository.stopStreaming(SensorId.RIGHT).getOrDefault(Unit)
                }
                stopResult = cameraDeferred.await()
                leftDeferred.await()
                rightDeferred.await()
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