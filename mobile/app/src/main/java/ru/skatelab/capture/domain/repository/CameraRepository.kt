package ru.skatelab.capture.domain.repository

import android.view.Surface
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow
import java.io.File

interface CameraRepository {
    val isRecording: Flow<Boolean>
    val frameTimestamps: Flow<Long>
    val currentFps: Flow<Int>
    val hardwareLevel: Flow<Int>
    val previewSurface: StateFlow<Surface?>

    /** Set preview surface for Camera2-based recorder. */
    fun setPreviewSurface(surface: Surface?)

    /**
     * Set preview surface provider for CameraX-based recorder.
     * Accepts [androidx.camera.core.Preview.SurfaceProvider] as [Any]
     * to avoid CameraX dependency in the domain layer.
     */
    fun setPreviewSurfaceProvider(provider: Any?)

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
