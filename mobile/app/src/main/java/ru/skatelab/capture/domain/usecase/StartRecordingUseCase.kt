package ru.skatelab.capture.domain.usecase

import android.os.SystemClock
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject

class StartRecordingUseCase @Inject constructor(
    private val bleRepository: BleRepository,
    private val cameraRepository: CameraRepository,
) {
    /**
     * Starts a recording session. Camera must already be prepared via
     * [CameraRepository.prepare] before calling this.
     *
     * BLE streaming start for LEFT/RIGHT runs in parallel.
     */
    suspend operator fun invoke(
        outputDir: File,
        videoFile: File,
        framesFile: File,
        imuLeftFile: File,
        imuRightFile: File,
    ): Result<RecordingStartInfo> = runCatching {
        // 1. Start BLE streaming in parallel (IMU first per H28)
        val tImuStartSentNs = SystemClock.elapsedRealtimeNanos()
        val (leftResult, rightResult) = coroutineScope {
            val left = async { bleRepository.startStreaming(SensorId.LEFT) }
            val right = async { bleRepository.startStreaming(SensorId.RIGHT) }
            Pair(left.await(), right.await())
        }
        if (leftResult.isFailure || rightResult.isFailure) {
            throw Exception("BLE streaming start failed")
        }

        // 2. Start camera recording (prepare must have been called before)
        val cameraResult = cameraRepository.startRecording().getOrThrow()

        // 3. Compute IMU start delay
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
