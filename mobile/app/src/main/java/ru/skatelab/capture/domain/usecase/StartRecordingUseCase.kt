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
     * Camera and BLE streaming start run in parallel — they're independent
     * and parallel start saves ~650-750ms of wall-clock latency.
     */
    suspend operator fun invoke(
        outputDir: File,
        videoFile: File,
        framesFile: File,
        imuLeftFile: File,
        imuRightFile: File,
    ): Result<RecordingStartInfo> = runCatching {
        val tImuStartSentNs = SystemClock.elapsedRealtimeNanos()

        // Camera + BLE streaming all start concurrently
        val (leftResult, rightResult, cameraResult) = coroutineScope {
            val left = async { bleRepository.startStreaming(SensorId.LEFT) }
            val right = async { bleRepository.startStreaming(SensorId.RIGHT) }
            val cameraDeferred = async { cameraRepository.startRecording() }
            Triple(left.await(), right.await(), cameraDeferred.await())
        }
        if (leftResult.isFailure || rightResult.isFailure) {
            throw Exception("BLE streaming start failed: L=${leftResult.exceptionOrNull()?.message}, R=${rightResult.exceptionOrNull()?.message}")
        }
        val cameraData = cameraResult.getOrThrow()

        val imuStartDelayMs = mapOf(
            SensorId.LEFT to ((cameraData.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
            SensorId.RIGHT to ((cameraData.tFirstFrameNs - tImuStartSentNs) / 1_000_000),
        )

        RecordingStartInfo(
            t0Ns = cameraData.tFirstFrameNs,
            timestampSource = cameraData.timestampSource,
            videoStartDelayMs = cameraData.videoStartDelayMs,
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
