package ru.skatelab.capture.domain.usecase

import android.content.Context
import android.content.Intent
import android.os.SystemClock
import dagger.hilt.android.qualifiers.ApplicationContext
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.service.SensorRecordingService
import java.io.File
import javax.inject.Inject

class StartRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
    @ApplicationContext private val context: Context,
) {
    /**
     * Starts a recording session. Camera must already be prepared via
     * [CameraRepository.prepare] before calling this.
     *
     * @param outputDir Directory for output files.
     * @param videoFile Video output file (already passed to [CameraRepository.prepare]).
     * @param framesFile Frame timestamps CSV (already passed to [CameraRepository.prepare]).
     * @param imuLeftFile IMU left sensor output file.
     * @param imuRightFile IMU right sensor output file.
     */
    suspend operator fun invoke(
        outputDir: File,
        videoFile: File,
        framesFile: File,
        imuLeftFile: File,
        imuRightFile: File,
    ): Result<RecordingStartInfo> = runCatching {
        // 1. Start Foreground Service
        val serviceIntent = Intent(context, SensorRecordingService::class.java).apply {
            action = SensorRecordingService.ACTION_START
        }
        context.startForegroundService(serviceIntent)

        // 2. Start BLE streaming (IMU first per H28)
        val tImuStartSentNs = SystemClock.elapsedRealtimeNanos()
        val leftResult = bleRepository.startStreaming(SensorId.LEFT)
        val rightResult = bleRepository.startStreaming(SensorId.RIGHT)
        if (leftResult.isFailure || rightResult.isFailure) {
            throw Exception("BLE streaming start failed")
        }

        // 3. Start camera recording (prepare must have been called before)
        val cameraResult = cameraRepository.startRecording().getOrThrow()

        // 4. Compute IMU start delay
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
