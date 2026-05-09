package ru.skatelab.capture.domain.usecase

import android.content.Context
import android.content.Intent
import dagger.hilt.android.qualifiers.ApplicationContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject

data class RecordingStartInfo(
    val t0Ns: Long,
    val timestampSource: String,
    val videoStartDelayMs: Long,
)

class StartRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
    @ApplicationContext private val context: Context,
) {
    companion object {
        private const val FGS_ACTION = "ru.skatelab.capture.RECORDING"
    }

    suspend fun invoke(outputDir: File): Result<RecordingStartInfo> = runCatching {
        // 1. Start foreground service
        val intent = Intent(FGS_ACTION).setPackage(context.packageName)
        context.startService(intent)

        // 2. Start BLE streaming — IMU first per H28 spec, then both sensors
        val leftResult = bleRepository.startStreaming(SensorId.LEFT)
        leftResult.getOrThrow()
        val rightResult = bleRepository.startStreaming(SensorId.RIGHT)
        rightResult.getOrThrow()

        // 3. Start camera recording
        val videoFile = File(outputDir, "video.mp4")
        val tsFile = File(outputDir, "frame_timestamps.csv")
        cameraRepository.prepare(videoFile, tsFile).getOrThrow()
        val camResult = cameraRepository.startRecording().getOrThrow()

        RecordingStartInfo(
            t0Ns = camResult.tStartCalledNs,
            timestampSource = camResult.timestampSource,
            videoStartDelayMs = camResult.videoStartDelayMs,
        )
    }
}
