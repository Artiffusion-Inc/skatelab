package ru.skatelab.capture.presentation.recording

import android.content.Context
import android.view.Surface
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.recording.ImuCollector
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.usecase.RecordingStartInfo
import ru.skatelab.capture.domain.usecase.StartRecordingUseCase
import ru.skatelab.capture.domain.usecase.StopRecordingUseCase
import java.io.File
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class RecordingViewModel @Inject constructor(
    private val cameraRepository: CameraRepository,
    private val imuCollector: ImuCollector,
    private val sessionRepository: SessionRepository,
    private val startRecordingUseCase: StartRecordingUseCase,
    private val stopRecordingUseCase: StopRecordingUseCase,
    private val appLogger: AppLogger,
) : ViewModel() {

    companion object {
        private const val TAG = "RecordingVM"
    }

    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording

    private val _isPreviewReady = MutableStateFlow(false)
    val isPreviewReady: StateFlow<Boolean> = _isPreviewReady

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private val _sessionId = MutableStateFlow<String?>(null)
    val sessionId: StateFlow<String?> = _sessionId

    private var currentStartInfo: RecordingStartInfo? = null
    private var currentCalibration = mapOf<SensorId, CalibrationData>()
    private var currentOutputDir: File? = null

    // File paths generated during prepareCamera, reused in startRecording
    private var preparedVideoFile: File? = null
    private var preparedFramesFile: File? = null
    private var preparedImuLeftFile: File? = null
    private var preparedImuRightFile: File? = null

    /**
     * Prepare camera for recording. Sets [isPreviewReady] on success.
     * Must be called before [startRecording].
     */
    fun prepareCamera(outputDir: File) {
        currentOutputDir = outputDir
        val timestamp = System.currentTimeMillis()
        val videoFile = File(outputDir, "${timestamp}.mp4")
        val framesFile = File(outputDir, "${timestamp}_frames.csv")
        val imuLeftFile = File(outputDir, "${timestamp}_left.binpb")
        val imuRightFile = File(outputDir, "${timestamp}_right.binpb")

        preparedVideoFile = videoFile
        preparedFramesFile = framesFile
        preparedImuLeftFile = imuLeftFile
        preparedImuRightFile = imuRightFile

        viewModelScope.launch {
            cameraRepository.prepare(videoFile, framesFile)
                .onSuccess {
                    _isPreviewReady.value = true
                    appLogger.i(TAG, "Camera prepared: $videoFile")
                }
                .onFailure {
                    _error.value = "Camera prepare failed: ${it.message}"
                    appLogger.e(TAG, "Camera prepare failed: ${it.message}")
                }
        }
    }

    fun startRecording(outputDir: File, calibration: Map<SensorId, CalibrationData>, context: Context) {
        currentCalibration = calibration
        currentOutputDir = outputDir

        val videoFile = preparedVideoFile ?: run {
            _error.value = "Camera not prepared"
            return
        }
        val framesFile = preparedFramesFile ?: run {
            _error.value = "Camera not prepared"
            return
        }
        val imuLeftFile = preparedImuLeftFile ?: run {
            _error.value = "IMU files not prepared"
            return
        }
        val imuRightFile = preparedImuRightFile ?: run {
            _error.value = "IMU files not prepared"
            return
        }

        if (!_isPreviewReady.value) {
            _error.value = "Camera not prepared"
            return
        }

        viewModelScope.launch {
            // Start IMU collector before use case starts BLE streaming
            imuCollector.start(
                viewModelScope,
                mapOf(SensorId.LEFT to imuLeftFile, SensorId.RIGHT to imuRightFile),
            )

            startRecordingUseCase(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)
                .onSuccess { startInfo ->
                    currentStartInfo = startInfo
                    _isRecording.value = true
                    appLogger.i(
                        TAG,
                        "Recording started: t0=${startInfo.t0Ns}, videoDelay=${startInfo.videoStartDelayMs}ms"
                    )
                }
                .onFailure {
                    imuCollector.stop()
                    _error.value = "Recording start failed: ${it.message}"
                    appLogger.e(TAG, "Recording start failed: ${it.message}")
                }
        }
    }

    fun stopRecording(context: Context) {
        val outputDir = currentOutputDir ?: run {
            _error.value = "No active recording"
            return
        }
        val startInfo = currentStartInfo ?: run {
            _error.value = "No recording info"
            return
        }

        viewModelScope.launch {
            // 1. Stop camera + BLE + release + FGS via use case
            stopRecordingUseCase()
                .onFailure {
                    appLogger.w(TAG, "Stop use case partial failure: ${it.message}")
                }

            _isRecording.value = false

            // 2. Stop IMU collection
            val imuCounts = imuCollector.stop()
            appLogger.i(TAG, "IMU samples: $imuCounts")

            // 3. Build and save session
            val durationMs = if (startInfo.t0Ns > 0) {
                (System.nanoTime() - startInfo.t0Ns) / 1_000_000
            } else 0L

            val session = CaptureSession(
                id = UUID.randomUUID().toString(),
                videoFile = startInfo.videoFile,
                imuLeftFile = startInfo.imuLeftFile,
                imuRightFile = startInfo.imuRightFile,
                frameTimestampsFile = startInfo.framesFile,
                manifestFile = File(outputDir, "manifest.json"),
                t0Ns = startInfo.t0Ns,
                durationMs = durationMs,
                videoFps = 60,
                timestampSource = startInfo.timestampSource,
                videoStartDelayMs = startInfo.videoStartDelayMs,
                imuStartDelayMs = startInfo.imuStartDelayMs,
                calibration = currentCalibration,
                createdAt = System.currentTimeMillis(),
                isComplete = startInfo.videoFile.exists() &&
                    (startInfo.imuLeftFile.exists() || startInfo.imuRightFile.exists()),
            )

            sessionRepository.saveSession(session)
                .onFailure { appLogger.e(TAG, "Session save failed: ${it.message}") }
            _sessionId.value = session.id
            _isPreviewReady.value = false
            currentStartInfo = null
            appLogger.i(TAG, "Recording stopped: ${session.id} complete=${session.isComplete}")
        }
    }

    /**
     * Set the preview surface for Camera2-based recorder.
     * Must be called before [prepareCamera] for the preview to appear.
     */
    fun setPreviewSurface(surface: Surface?) {
        cameraRepository.setPreviewSurface(surface)
    }

    /**
     * Set the preview surface provider for CameraX-based recorder.
     * Accepts [androidx.camera.core.Preview.SurfaceProvider] as [Any]
     * to avoid CameraX dependency in the ViewModel.
     * Must be called before [prepareCamera] for the preview to appear.
     */
    fun setPreviewSurfaceProvider(provider: Any?) {
        cameraRepository.setPreviewSurfaceProvider(provider)
    }

    override fun onCleared() {
        super.onCleared()
        viewModelScope.launch {
            cameraRepository.release()
        }
    }
}
