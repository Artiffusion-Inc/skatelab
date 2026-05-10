package ru.skatelab.capture.data.camera

import android.content.Context
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CameraRepositoryImpl @Inject constructor(
    private val context: Context,
) : CameraRepository {

    private val _isRecording = MutableStateFlow(false)
    private val _frameTimestamps = MutableSharedFlow<Long>()
    private val _currentFps = MutableStateFlow(0)
    private val _hardwareLevel = MutableStateFlow(-1)

    private var recorder: Camera2Recorder? = null

    override val isRecording: Flow<Boolean> = _isRecording
    override val frameTimestamps: Flow<Long> = _frameTimestamps
    override val currentFps: Flow<Int> = _currentFps
    override val hardwareLevel: Flow<Int> = _hardwareLevel

    override suspend fun prepare(outputFile: File, timestampsFile: File): Result<Unit> = runCatching {
        val rec = Camera2Recorder(context)
        rec.openCamera()
        _hardwareLevel.value = rec.getHardwareLevel()
        rec.prepare(outputFile, timestampsFile, previewSurface = null)
        recorder = rec
    }

    override suspend fun startRecording(): Result<CameraRepository.RecordingStartResult> = runCatching {
        val rec = recorder ?: throw IllegalStateException("Camera not prepared")
        _isRecording.value = true
        val result = rec.startRecording()
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
