package ru.skatelab.capture.domain.repository

import androidx.lifecycle.LifecycleOwner
import java.io.File
import kotlinx.coroutines.flow.StateFlow

interface CameraRepository {
    val isPreviewReady: StateFlow<Boolean>
    val isRecording: StateFlow<Boolean>

    /** Bind CameraX use cases to [lifecycleOwner]. Must be called before recording. */
    suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit>

    /** Unbind all use cases and release camera. */
    suspend fun unbind()

    /** Start recording to [videoFile] with frame timestamps in [framesFile]. */
    suspend fun startRecording(
        videoFile: File,
        framesFile: File,
    ): Result<RecordingStartResult>

    /** Stop active recording. Non-blocking — uses CameraX VideoRecordEvent flow. */
    suspend fun stopRecording(): Result<RecordingStopResult>

    /** Release all camera resources. */
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