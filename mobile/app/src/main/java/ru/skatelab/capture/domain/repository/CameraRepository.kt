package ru.skatelab.capture.domain.repository

import kotlinx.coroutines.flow.Flow
import java.io.File

interface CameraRepository {
    val isRecording: Flow<Boolean>
    val frameTimestamps: Flow<Long>
    val currentFps: Flow<Int>
    val hardwareLevel: Flow<Int>

    suspend fun prepare(outputFile: File, timestampsFile: File): Result<Unit>
    suspend fun startRecording(): Result<RecordingStartResult>
    suspend fun stopRecording(): Result<RecordingStopResult>
    suspend fun release()

    data class RecordingStartResult(
        val tStartCalledNs: Long,
        val tFirstFrameNs: Long,
        val timestampSource: String,
        val videoStartDelayMs: Long,
    )

    data class RecordingStopResult(
        val actualFps: Int,
        val fpsVerified: Boolean,
    )
}
