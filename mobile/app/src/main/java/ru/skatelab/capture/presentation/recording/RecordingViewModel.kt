package ru.skatelab.capture.presentation.recording

import android.content.Context
import android.content.Intent
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.recording.ImuCollector
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import java.io.File
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class RecordingViewModel @Inject constructor(
    private val bleRepository: BleRepository,
    private val imuCollector: ImuCollector,
    private val sessionRepository: SessionRepository,
    private val appLogger: AppLogger,
) : ViewModel() {

    companion object {
        private const val TAG = "RecordingVM"
        private const val FGS_ACTION = "ru.skatelab.capture.RECORDING"
    }

    private var cameraProvider: ProcessCameraProvider? = null
    private var recorder: Recorder? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var activeRecording: Recording? = null

    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording

    private val _isPreviewReady = MutableStateFlow(false)
    val isPreviewReady: StateFlow<Boolean> = _isPreviewReady

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private val _sessionId = MutableStateFlow<String?>(null)
    val sessionId: StateFlow<String?> = _sessionId

    private var currentOutputDir: File? = null
    private var currentT0Ns = 0L
    private var currentCalibration = mapOf<SensorId, CalibrationData>()
    private var connectedSensors: Set<SensorId> = emptySet()
    private var currentImuStartDelays: Map<SensorId, Long> = emptyMap()
    private var currentVideoStartDelayMs = 0L

    fun startPreview(previewView: PreviewView, lifecycleOwner: LifecycleOwner) {
        val context = previewView.context
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            cameraProvider = future.get()
            bindUseCases(cameraProvider!!, previewView, lifecycleOwner)
            _isPreviewReady.value = true
        }, ContextCompat.getMainExecutor(context))
    }

    private fun bindUseCases(
        provider: ProcessCameraProvider,
        previewView: PreviewView,
        lifecycleOwner: LifecycleOwner,
    ) {
        val preview = Preview.Builder().build().also {
            it.setSurfaceProvider(previewView.surfaceProvider)
        }

        recorder = Recorder.Builder()
            .setQualitySelector(QualitySelector.from(Quality.FHD))
            .build()
        videoCapture = VideoCapture.withOutput(recorder!!)

        val selector = CameraSelector.Builder()
            .requireLensFacing(CameraSelector.LENS_FACING_BACK)
            .build()

        try {
            provider.unbindAll()
            provider.bindToLifecycle(lifecycleOwner, selector, preview, videoCapture)
            appLogger.i(TAG, "Camera use cases bound: preview + video")
        } catch (e: Exception) {
            appLogger.e(TAG, "Camera bind failed: ${e.message}")
            try {
                provider.unbindAll()
                provider.bindToLifecycle(lifecycleOwner, selector, preview)
                videoCapture = null
                appLogger.w(TAG, "Fell back to preview-only (no video capture)")
            } catch (e2: Exception) {
                appLogger.e(TAG, "Preview-only also failed: ${e2.message}")
            }
        }
    }

    fun stopPreview() {
        cameraProvider?.unbindAll()
        _isPreviewReady.value = false
    }

    fun startRecording(outputDir: File, calibration: Map<SensorId, CalibrationData>, context: Context) {
        currentCalibration = calibration
        currentOutputDir = outputDir

        val rec = recorder ?: run {
            _error.value = "Video capture not available"
            return
        }
        val capture = videoCapture ?: run {
            _error.value = "Video capture not bound"
            return
        }

        outputDir.mkdirs()
        val videoFile = File(outputDir, "video.mp4")

        // Start FGS
        val intent = Intent(FGS_ACTION).setPackage(context.packageName)
        androidx.core.content.ContextCompat.startForegroundService(context, intent)

        viewModelScope.launch {
            // Determine connected sensors
            val connState = bleRepository.connectionState.first()
            val sensors = mutableSetOf<SensorId>()
            if (connState[SensorId.LEFT] == BleRepository.ConnectionState.CONNECTED) {
                sensors.add(SensorId.LEFT)
            }
            if (connState[SensorId.RIGHT] == BleRepository.ConnectionState.CONNECTED) {
                sensors.add(SensorId.RIGHT)
            }
            connectedSensors = sensors

            // Open IMU writers
            val imuFiles = mutableMapOf<SensorId, File>()
            for (sensorId in sensors) {
                val file = when (sensorId) {
                    SensorId.LEFT -> File(outputDir, "imu_left.binpb")
                    SensorId.RIGHT -> File(outputDir, "imu_right.binpb")
                }
                imuFiles[sensorId] = file
            }
            imuCollector.start(viewModelScope, imuFiles)

            // Start BLE streaming
            for (sensorId in sensors) {
                bleRepository.startStreaming(sensorId).getOrElse {
                    appLogger.w(TAG, "$sensorId streaming failed: ${it.message}")
                }
            }

            // Record IMU start time for delay calculation
            val imuStartNs = System.nanoTime()
            currentImuStartDelays = sensors.associateWith { 0L }

            // Start video recording
            currentT0Ns = System.nanoTime()
            try {
                val fileOutputOptions = FileOutputOptions.Builder(videoFile).build()
                val pendingRecording = rec.prepareRecording(context, fileOutputOptions)
                activeRecording = pendingRecording.start(
                    ContextCompat.getMainExecutor(context)
                ) { event ->
                    when (event) {
                        is VideoRecordEvent.Start -> {
                            _isRecording.value = true
                            val videoStartNs = System.nanoTime()
                            currentVideoStartDelayMs = (videoStartNs - currentT0Ns) / 1_000_000
                            currentImuStartDelays = sensors.associateWith {
                                (currentT0Ns - imuStartNs) / 1_000_000
                            }
                            appLogger.i(TAG, "Video recording started, videoStartDelay=${currentVideoStartDelayMs}ms, imuStartDelay=${currentImuStartDelays}ms")
                        }
                        is VideoRecordEvent.Finalize -> {
                            if (!event.hasError()) {
                                appLogger.i(TAG, "Video saved: ${event.outputResults.outputUri}")
                            } else {
                                appLogger.e(TAG, "Video error: ${event.cause}")
                                _error.value = "Video recording error"
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                _error.value = "Failed to start video: ${e.message}"
                appLogger.e(TAG, "Video start failed: ${e.message}")
            }
        }
    }

    fun stopRecording(context: Context) {
        val outputDir = currentOutputDir ?: run {
            _error.value = "No active recording"
            return
        }

        viewModelScope.launch {
            // 1. Stop video
            activeRecording?.stop()
            activeRecording = null
            _isRecording.value = false

            // 2. Stop IMU collection
            val imuCounts = imuCollector.stop()
            appLogger.i(TAG, "IMU samples: $imuCounts")

            // 3. Stop BLE streaming
            for (sensorId in connectedSensors) {
                bleRepository.stopStreaming(sensorId).getOrElse {
                    appLogger.w(TAG, "$sensorId stopStreaming failed: ${it.message}")
                }
            }

            // 4. Stop FGS
            context.stopService(Intent(FGS_ACTION).setPackage(context.packageName))

            // 5. Build and save session
            val videoFile = File(outputDir, "video.mp4")
            val imuLeftFile = File(outputDir, "imu_left.binpb")
            val imuRightFile = File(outputDir, "imu_right.binpb")
            val frameTimestampsFile = File(outputDir, "frame_timestamps.csv")
            val manifestFile = File(outputDir, "manifest.json")

            val durationMs = if (currentT0Ns > 0) (System.nanoTime() - currentT0Ns) / 1_000_000 else 0L

            // 5b. Write frame timestamps based on t0Ns + videoStartDelay + fps
            frameTimestampsFile.bufferedWriter().use { writer ->
                val fps = 60L
                val frameNs = 1_000_000_000L / fps
                val videoStartNs = currentT0Ns + currentVideoStartDelayMs * 1_000_000L
                val numFrames = durationMs * fps / 1000
                for (i in 0 until numFrames) {
                    writer.write("${videoStartNs + i * frameNs}\n")
                }
            }

            val session = CaptureSession(
                id = UUID.randomUUID().toString(),
                videoFile = videoFile,
                imuLeftFile = imuLeftFile,
                imuRightFile = imuRightFile,
                frameTimestampsFile = frameTimestampsFile,
                manifestFile = manifestFile,
                t0Ns = currentT0Ns,
                durationMs = durationMs,
                videoFps = 60,
                timestampSource = "camerax",
                videoStartDelayMs = currentVideoStartDelayMs,
                imuStartDelayMs = currentImuStartDelays,
                calibration = currentCalibration,
                createdAt = System.currentTimeMillis(),
                isComplete = videoFile.exists() && (imuLeftFile.exists() || imuRightFile.exists()),
            )

            sessionRepository.saveSession(session)
            _sessionId.value = session.id
            appLogger.i(TAG, "Recording stopped: ${session.id} complete=${session.isComplete}")
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopPreview()
    }
}
