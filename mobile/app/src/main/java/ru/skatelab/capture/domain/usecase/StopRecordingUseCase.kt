package ru.skatelab.capture.domain.usecase

import android.content.Context
import android.content.Intent
import dagger.hilt.android.qualifiers.ApplicationContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.service.SensorRecordingService
import javax.inject.Inject

class StopRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
    @ApplicationContext private val context: Context,
) {
    suspend operator fun invoke(): Result<Unit> = runCatching {
        // 1. Stop camera
        cameraRepository.stopRecording().getOrThrow()

        // 2. Stop BLE streaming (best-effort — don't abort if one sensor fails)
        bleRepository.stopStreaming(SensorId.LEFT).getOrDefault(Unit)
        bleRepository.stopStreaming(SensorId.RIGHT).getOrDefault(Unit)

        // 3. Release camera
        cameraRepository.release()

        // 4. Stop Foreground Service
        val serviceIntent = Intent(context, SensorRecordingService::class.java).apply {
            action = SensorRecordingService.ACTION_STOP
        }
        context.startService(serviceIntent)
    }
}
