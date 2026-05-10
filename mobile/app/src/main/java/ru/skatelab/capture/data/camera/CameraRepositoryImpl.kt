package ru.skatelab.capture.data.camera

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class CameraRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
) : CameraRepository {

    private val _isRecording = MutableStateFlow(false)
    private val _frameTimestamps = MutableSharedFlow<Long>()
    private val _currentFps = MutableStateFlow(0)
    private val _hardwareLevel = MutableStateFlow(-1)

    /** Selected recorder — Camera2 for FULL/LEVEL_3, CameraX for LEGACY/LIMITED. */
    private var camera2Recorder: Camera2Recorder? = null
    private var cameraXRecorder: CameraXRecorder? = null
    private var useCameraX: Boolean = false

    override val isRecording: Flow<Boolean> = _isRecording
    override val frameTimestamps: Flow<Long> = _frameTimestamps
    override val currentFps: Flow<Int> = _currentFps
    override val hardwareLevel: Flow<Int> = _hardwareLevel

    override suspend fun prepare(outputFile: File, timestampsFile: File): Result<Unit> = runCatching {
        // Open camera via Camera2 to read hardware level, regardless of which
        // recorder we ultimately use. CameraXRecorder also needs openCamera()
        // to read characteristics before binding use cases.
        val hwLevel = probeHardwareLevel()

        _hardwareLevel.value = hwLevel

        // Camera2 is reliable on FULL (2) and LEVEL_3 (3) devices.
        // LEGACY (0) and LIMITED (1) devices often have broken Camera2 HALs —
        // CameraX handles quirks internally and is the safer fallback.
        useCameraX = hwLevel < CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_FULL

        if (useCameraX) {
            val rec = CameraXRecorder(context)
            rec.openCamera()
            rec.prepare(outputFile, timestampsFile, previewSurface = null)
            cameraXRecorder = rec
        } else {
            val rec = Camera2Recorder(context)
            rec.openCamera()
            rec.prepare(outputFile, timestampsFile, previewSurface = null)
            camera2Recorder = rec
        }
    }

    override suspend fun startRecording(): Result<CameraRepository.RecordingStartResult> = runCatching {
        val result = if (useCameraX) {
            val rec = cameraXRecorder ?: throw IllegalStateException("Camera not prepared")
            rec.startRecording()
        } else {
            val rec = camera2Recorder ?: throw IllegalStateException("Camera not prepared")
            rec.startRecording()
        }
        _isRecording.value = true
        _currentFps.value = 60
        result
    }

    override suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> = runCatching {
        val result = if (useCameraX) {
            val rec = cameraXRecorder ?: throw IllegalStateException("Camera not recording")
            rec.stopRecording()
        } else {
            val rec = camera2Recorder ?: throw IllegalStateException("Camera not recording")
            rec.stopRecording()
        }
        _isRecording.value = false
        _currentFps.value = 0
        result
    }

    override suspend fun release() {
        camera2Recorder?.release()
        cameraXRecorder?.release()
        camera2Recorder = null
        cameraXRecorder = null
    }

    /**
     * Opens the back camera via Camera2 [android.hardware.camera2.CameraManager]
     * to read [CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL] without
     * fully initializing a recorder. The value determines which recorder to use.
     */
    private fun probeHardwareLevel(): Int {
        val manager = context.getSystemService(Context.CAMERA_SERVICE)
            as android.hardware.camera2.CameraManager
        val backCameraId = manager.cameraIdList.firstOrNull { id ->
            manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        } ?: throw IllegalStateException("No back camera found")
        return manager.getCameraCharacteristics(backCameraId)
            .get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL) ?: 0
    }
}
