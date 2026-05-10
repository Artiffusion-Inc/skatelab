package ru.skatelab.capture.domain.usecase

import android.content.Context
import android.content.Intent
import android.os.SystemClock
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.service.SensorRecordingService
import java.io.File
import javax.inject.Inject

class StartRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
    private val context: Context,
) {
    suspend operator fun invoke(outputDir: File): Result<RecordingStartInfo> = runCatching {
        // 1. Start Foreground Service
        val serviceIntent = Intent(context, SensorRecordingService::class.java).apply {
            action = SensorRecordingService.ACTION_START
        }
        context.startForegroundService(serviceIntent)

        // 2. Prepare output files
        val timestamp = System.currentTimeMillis()
        val videoFile = File(outputDir, "${timestamp}.mp4")
        val framesFile = File(outputDir, "${timestamp}_frames.csv")
        val imuLeftFile = File(outputDir, "${timestamp}_left.binpb")
        val imuRightFile = File(outputDir, "${timestamp}_right.binpb")

        // 3. Start BLE streaming (IMU first per H28)
        val tImuStartSentNs = SystemClock.elapsedRealtimeNanos()
        val leftResult = bleRepository.startStreaming(SensorId.LEFT)
        val rightResult = bleRepository.startStreaming(SensorId.RIGHT)
        if (leftResult.isFailure || rightResult.isFailure) {
            throw Exception("BLE streaming start failed")
        }

        // 4. Start camera (after IMU per H28)
        cameraRepository.prepare(videoFile, framesFile).getOrThrow()
        val cameraResult = cameraRepository.startRecording().getOrThrow()

        // 5. Compute IMU start delay (simplified — actual first arrival tracked via Flow in real impl)
        val imuStartDelayMs = mapOf(
            SensorId.LEFT to ((cameraResult.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
            SensorId.RIGHT to ((cameraResult.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
        )

        RecordingStartInfo(
            t0Ns = cameraResult.tFirstFrameNs,
            timestampSource = cameraResult.timestampSource,
            videoStartDelayMs = cameraResult.videoStartDelayMs,
            imuStartDelayMs = imuStartDelayMs,
            videoFile = videoFile,
            imuLeftFile = imuLeftFile,
            imuRightFile = imuRightFile,
            framesFile = framesFile,
        )
    }
}

data class RecordingStartInfo(
    val t0Ns: Long,
    val timestampSource: String,
    val videoStartDelayMs: Long,
    val imuStartDelayMs: Map<SensorId, Long>,
    val videoFile: File,
    val imuLeftFile: File,
    val imuRightFile: File,
    val framesFile: File,
)
