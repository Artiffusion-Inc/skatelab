package ru.skatelab.capture.ui.camera

import android.content.Context
import android.os.Environment
import androidx.camera.core.SurfaceRequest
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.R
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.BleRepository.ConnectionState
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.service.ImuCollector
import ru.skatelab.capture.domain.usecase.ReadSensorInfoUseCase
import ru.skatelab.capture.domain.usecase.RecordingStartInfo
import ru.skatelab.capture.domain.usecase.StartRecordingUseCase
import ru.skatelab.capture.domain.usecase.StopRecordingUseCase
import ru.skatelab.capture.upload.UploadScheduler

@HiltViewModel
class CameraViewModel
    @Inject
    constructor(
        private val cameraRepository: CameraRepository,
        private val bleRepository: BleRepository,
        private val startRecordingUseCase: StartRecordingUseCase,
        private val stopRecordingUseCase: StopRecordingUseCase,
        private val readSensorInfoUseCase: ReadSensorInfoUseCase,
        private val imuCollector: ImuCollector,
        private val pendingUploadDao: PendingUploadDao,
        private val appLogger: Logger,
        @ApplicationContext private val appContext: Context,
    ) : ViewModel() {
        companion object {
            private const val TAG = "CameraVM"
        }

        private val _isRecording = MutableStateFlow(false)
        val isRecording: StateFlow<Boolean> = _isRecording

        private val _isPreviewReady = MutableStateFlow(false)
        val isPreviewReady: StateFlow<Boolean> = _isPreviewReady

        private val _error = MutableStateFlow<String?>(null)
        val error: StateFlow<String?> = _error

        private val _elapsedMs = MutableStateFlow(0L)
        val elapsedMs: StateFlow<Long> = _elapsedMs

        private val _bleConnected = MutableStateFlow(false)
        val bleConnected: StateFlow<Boolean> = _bleConnected

        private val _sensorInfo = MutableStateFlow<Map<SensorId, SensorInfo?>>(emptyMap())
        val sensorInfo: StateFlow<Map<SensorId, SensorInfo?>> = _sensorInfo

        private val _reconnectingSensor = MutableStateFlow<SensorId?>(null)
        val reconnectingSensor: StateFlow<SensorId?> = _reconnectingSensor

        private val _navigateToProcessing = MutableStateFlow<String?>(null)
        val navigateToProcessing: StateFlow<String?> = _navigateToProcessing

        private val _pendingElementType = MutableStateFlow<String?>(null)
        val pendingElementType: StateFlow<String?> = _pendingElementType

        private val _pendingUploadId = MutableStateFlow<String?>(null)
        val pendingUploadId: StateFlow<String?> = _pendingUploadId

        private val _galleryUploadError = MutableStateFlow<String?>(null)
        val galleryUploadError: StateFlow<String?> = _galleryUploadError

        fun setGalleryUploadError(message: String?) {
            _galleryUploadError.value = message
        }

        val surfaceRequest: StateFlow<SurfaceRequest?> = cameraRepository.surfaceRequest

        private var currentStartInfo: RecordingStartInfo? = null
        private var currentOutputDir: File? = null
        private var preparedVideoFile: File? = null
        private var preparedFramesFile: File? = null
        private var preparedImuLeftFile: File? = null
        private var preparedImuRightFile: File? = null
        private var timerJob: kotlinx.coroutines.Job? = null
        private var recordingStartNanos: Long = 0L
        private var batteryJob: kotlinx.coroutines.Job? = null
        private var reconnectJob: kotlinx.coroutines.Job? = null

        fun bindCamera(lifecycleOwner: LifecycleOwner) {
            val outputDir =
                File(
                    appContext.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),
                    "skatelab_capture_${System.currentTimeMillis()}",
                ).also { it.mkdirs() }
            currentOutputDir = outputDir

            cleanupStaleCaptureDirs(outputDir.parentFile, excludeDir = outputDir)

            val timestamp = System.currentTimeMillis()
            preparedVideoFile = File(outputDir, "$timestamp.mp4")
            preparedFramesFile = File(outputDir, "${timestamp}_frames.csv")
            preparedImuLeftFile = File(outputDir, "${timestamp}_left.binpb")
            preparedImuRightFile = File(outputDir, "${timestamp}_right.binpb")

            viewModelScope.launch {
                cameraRepository
                    .bindToLifecycle(lifecycleOwner)
                    .onSuccess {
                        _isPreviewReady.value = true
                        appLogger.i(TAG, "Camera bound to lifecycle")
                    }.onFailure {
                        _error.value = "Camera prepare failed: ${it.message}"
                        appLogger.e(TAG, "Camera prepare failed: ${it.message}")
                    }
            }
        }

        fun startRecording(context: Context) {
            val videoFile =
                preparedVideoFile ?: run {
                    _error.value = "Camera not prepared"
                    return
                }
            val framesFile =
                preparedFramesFile ?: run {
                    _error.value = "Camera not prepared"
                    return
                }
            val imuLeftFile =
                preparedImuLeftFile ?: run {
                    _error.value = "IMU files not prepared"
                    return
                }
            val imuRightFile =
                preparedImuRightFile ?: run {
                    _error.value = "IMU files not prepared"
                    return
                }
            val outputDir =
                currentOutputDir ?: run {
                    _error.value = "No output directory"
                    return
                }

            if (!isPreviewReady.value) {
                _error.value = "Camera not prepared"
                return
            }

            viewModelScope.launch {
                // Start file writers before enabling BLE streaming so the first
                // notifications belong to this capture and are persisted.
                imuCollector.start(
                    viewModelScope,
                    mapOf(
                        SensorId.LEFT to imuLeftFile,
                        SensorId.RIGHT to imuRightFile,
                    ),
                )
                startRecordingUseCase(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)
                    .onSuccess { startInfo ->
                        currentStartInfo = startInfo
                        _isRecording.value = true
                        startReconnectWatch()
                        startTimer()
                        appLogger.i(TAG, "Recording started: t0=${startInfo.t0Ns}")
                    }.onFailure {
                        imuCollector.stop()
                        _error.value = "Recording start failed: ${it.message}"
                        appLogger.e(TAG, "Recording start failed: ${it.message}")
                    }
            }
        }

        fun stopRecording(context: Context) {
            viewModelScope.launch {
                stopReconnectWatch()
                stopTimer()

                stopRecordingUseCase()
                    .onFailure {
                        appLogger.w(TAG, "Stop use case partial failure: ${it.message}")
                    }

                val imuCounts = imuCollector.stop()
                appLogger.i(TAG, "IMU capture stopped: $imuCounts")

                // Persist a capture manifest before WorkManager can upload the session.
                // Keep it deliberately schema-light until the full calibration metadata
                // is available in this camera flow; the filenames and timing anchor are
                // enough to make the uploaded artifacts addressable and debuggable.
                val manifestFile = File(outputDir, "manifest.json")
                manifestFile.writeText(
                    """{
  \"version\": \"2.0\",
  \"t0_ns\": ${startInfo.t0Ns},
  \"duration_ms\": ${_elapsedMs.value},
  \"video\": {\"filename\": \"${startInfo.videoFile.name}\", \"frames\": \"${startInfo.framesFile.name}\"},
  \"imu\": {
    \"left\": {\"filename\": \"${startInfo.imuLeftFile.name}\", \"sensor_id\": \"LEFT\"},
    \"right\": {\"filename\": \"${startInfo.imuRightFile.name}\", \"sensor_id\": \"RIGHT\"}
  }
}""".trimIndent(),
                )

                _isRecording.value = false

                val startInfo =
                    currentStartInfo ?: run {
                        _error.value = "No recording info"
                        return@launch
                    }
                val outputDir = currentOutputDir ?: return@launch

                // Create a PendingUpload in Room for later upload
                val uploadId = UUID.randomUUID().toString()
                val pendingUpload =
                    PendingUploadEntity(
                        id = uploadId,
                        videoPath = startInfo.videoFile.absolutePath,
                        imuLeftPath = startInfo.imuLeftFile.absolutePath,
                        imuRightPath = startInfo.imuRightFile.absolutePath,
                        manifestPath = File(outputDir, "manifest.json").absolutePath,
                        status = "READY",
                    )
                pendingUploadDao.insert(pendingUpload)
                appLogger.i(TAG, "PendingUpload saved: $uploadId")

                // Enqueue upload with network constraints
                UploadScheduler.enqueue(appContext, uploadId)

                // Show element type selection before navigating
                _pendingElementType.value = "axel"
                _pendingUploadId.value = uploadId

                currentStartInfo = null
                _isPreviewReady.value = false

                // Re-bind camera for next recording
                // (The LifecycleOwner is still active, so we re-bind)
            }
        }

        fun toggleRecording(context: Context) {
            if (_isRecording.value) {
                stopRecording(context)
            } else {
                startRecording(context)
            }
        }

        fun confirmElementType(
            uploadId: String,
            elementType: String,
        ) {
            viewModelScope.launch {
                val entity = pendingUploadDao.getById(uploadId) ?: return@launch
                pendingUploadDao.insert(entity.copy(elementType = elementType))
                _pendingElementType.value = null
                _pendingUploadId.value = null
                _navigateToProcessing.value = uploadId
            }
        }

        fun onNavigatedToProcessing() {
            _navigateToProcessing.value = null
        }

        fun cancelElementTypeSelection() {
            _pendingElementType.value = null
            _pendingUploadId.value = null
        }

        fun createGalleryUpload(
            videoPath: String,
            elementType: String?,
        ) {
            viewModelScope.launch {
                val error = validateVideoFile(videoPath)
                if (error != null) {
                    _galleryUploadError.value = error
                    return@launch
                }

                val uploadId = UUID.randomUUID().toString()
                val pendingUpload =
                    PendingUploadEntity(
                        id = uploadId,
                        videoPath = videoPath,
                        elementType = elementType,
                        status = "READY",
                    )
                pendingUploadDao.insert(pendingUpload)
                appLogger.i(TAG, "Gallery upload saved: $uploadId")
                UploadScheduler.enqueue(appContext, uploadId)
                _navigateToProcessing.value = uploadId
            }
        }

        internal fun validateVideoFile(path: String): String? {
            val file = File(path)
            if (!file.exists()) return appContext.getString(R.string.upload_error_file_not_found)
            val ext = file.extension.lowercase()
            if (ext !in listOf("mp4", "mov", "3gp", "webm", "mkv")) {
                return appContext.getString(R.string.upload_error_unsupported_format, ext)
            }
            val maxSizeMb = 100
            if (file.length() > maxSizeMb * 1024L * 1024L) {
                val sizeMb = file.length() / (1024L * 1024L)
                return appContext.getString(R.string.upload_error_file_too_large, sizeMb, maxSizeMb)
            }
            return null
        }

        fun startBatteryPolling() {
            batteryJob?.cancel()
            batteryJob =
                viewModelScope.launch {
                    while (true) {
                        refreshBattery()
                        kotlinx.coroutines.delay(30_000L)
                    }
                }
        }

        fun startBleMonitoring() {
            viewModelScope.launch {
                bleRepository.connectionState.collect { stateMap ->
                    val leftState = stateMap[SensorId.LEFT]
                    val rightState = stateMap[SensorId.RIGHT]
                    _bleConnected.value = leftState == ConnectionState.CONNECTED || rightState == ConnectionState.CONNECTED
                }
            }
        }

        private suspend fun refreshBattery() {
            for (sensorId in listOf(SensorId.LEFT, SensorId.RIGHT)) {
                val result = readSensorInfoUseCase(sensorId)
                if (result.isSuccess) {
                    _sensorInfo.value = _sensorInfo.value + (sensorId to result.getOrThrow())
                }
            }
        }

        private fun startReconnectWatch() {
            reconnectJob?.cancel()
            reconnectJob =
                viewModelScope.launch {
                    bleRepository.reconnectEvents.collect { sensorId ->
                        _reconnectingSensor.value = sensorId
                        appLogger.w(TAG, "BLE reconnecting: $sensorId")
                        kotlinx.coroutines.delay(3_000L)
                        _reconnectingSensor.value = null
                    }
                }
        }

        private fun stopReconnectWatch() {
            reconnectJob?.cancel()
            reconnectJob = null
            _reconnectingSensor.value = null
        }

        private fun startTimer() {
            recordingStartNanos = System.nanoTime()
            timerJob?.cancel()
            timerJob =
                viewModelScope.launch {
                    while (_isRecording.value) {
                        _elapsedMs.value = (System.nanoTime() - recordingStartNanos) / 1_000_000
                        kotlinx.coroutines.delay(200L)
                    }
                }
        }

        private fun stopTimer() {
            timerJob?.cancel()
            timerJob = null
            _elapsedMs.value = 0L
        }

        private fun cleanupStaleCaptureDirs(
            parentDir: File?,
            excludeDir: File,
        ) {
            if (parentDir == null || !parentDir.exists()) return
            parentDir
                .listFiles()
                ?.filter { it.isDirectory && it.name.startsWith("skatelab_capture_") && it != excludeDir }
                ?.forEach { dir ->
                    val hasVideo = dir.listFiles()?.any { it.extension == "mp4" } ?: false
                    if (!hasVideo) {
                        dir.deleteRecursively()
                        appLogger.i(TAG, "Cleaned up stale capture dir: ${dir.name}")
                    }
                }
        }

        override fun onCleared() {
            super.onCleared()
            batteryJob?.cancel()
            timerJob?.cancel()
            reconnectJob?.cancel()
            kotlinx.coroutines.runBlocking(Dispatchers.IO) {
                try {
                    cameraRepository.release()
                } catch (e: Exception) {
                    appLogger.e(TAG, "onCleared camera release failed: ${e.message}")
                }
            }
        }
    }
