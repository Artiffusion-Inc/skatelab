package ru.skatelab.capture.data.camera

import android.content.Context
import android.view.Surface
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CameraRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
) : CameraRepository {

    private val _isRecording = MutableStateFlow(false)
    private val _currentFps = MutableStateFlow(0)
    private val _hardwareLevel = MutableStateFlow(-1)
    private val _previewSurface = MutableStateFlow<Surface?>(null)

    private var recorder: Camera2Recorder? = null

    override val isRecording: Flow<Boolean> = _isRecording
    override val frameTimestamps: Flow<Long> = MutableStateFlow(0L)
    override val currentFps: Flow<Int> = _currentFps
    override val hardwareLevel: Flow<Int> = _hardwareLevel
    override val previewSurface: StateFlow<Surface?> = _previewSurface.asStateFlow()

    override fun setPreviewSurface(surface: Surface?) {
        val prev = _previewSurface.value
        _previewSurface.value = surface

        // If surface was destroyed, close camera session to prevent BufferQueue abandoned errors
        if (surface == null && prev != null) {
            recorder?.closeSession()
        }
    }

    override suspend fun prepare(outputFile: File, timestampsFile: File): Result<Unit> = runCatching {
        val rec = Camera2Recorder(context)
        rec.openCamera()
        _hardwareLevel.value = rec.getHardwareLevel()
        rec.prepare(
            outputFile = outputFile,
            timestampsFile = timestampsFile,
            previewSurface = _previewSurface.value,
        )
        recorder = rec
    }

    override suspend fun restartPreview(): Result<Unit> = runCatching {
        val rec = recorder ?: throw IllegalStateException("Camera not prepared")
        rec.startPreview(_previewSurface.value)
    }

    override suspend fun startRecording(): Result<CameraRepository.RecordingStartResult> = runCatching {
        val rec = recorder ?: throw IllegalStateException("Camera not prepared")
        val result = rec.startRecording()
        _isRecording.value = true
        _currentFps.value = 60
        result
    }

    override suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> = runCatching {
        val rec = recorder ?: throw IllegalStateException("Camera not recording")
        val result = rec.stopRecording()
        _isRecording.value = false
        _currentFps.value = 0
        result
    }

    override suspend fun release() {
        recorder?.release()
        recorder = null
    }
}
