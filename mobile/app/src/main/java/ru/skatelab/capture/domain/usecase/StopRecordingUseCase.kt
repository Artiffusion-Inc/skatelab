package ru.skatelab.capture.domain.usecase

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import javax.inject.Inject

class StopRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
    @ApplicationContext private val context: Context,
) {
    suspend fun invoke(): Result<Unit> = runCatching {
        cameraRepository.stopRecording().getOrThrow()
        bleRepository.stopStreaming(SensorId.LEFT).getOrThrow()
        bleRepository.stopStreaming(SensorId.RIGHT).getOrThrow()
        cameraRepository.release()
        context.stopService(
            android.content.Intent("ru.skatelab.capture.RECORDING").setPackage(context.packageName)
        )
    }
}
