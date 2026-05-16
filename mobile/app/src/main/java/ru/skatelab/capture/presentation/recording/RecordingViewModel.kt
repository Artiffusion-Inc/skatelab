package ru.skatelab.capture.presentation.recording

import android.content.Context
import android.content.Intent
import androidx.camera.core.SurfaceRequest
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.service.ImuCollector
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.service.TimeSynchronizer
import ru.skatelab.capture.domain.usecase.ReadSensorInfoUseCase
import ru.skatelab.capture.domain.usecase.RecordingStartInfo
import ru.skatelab.capture.domain.usecase.StartRecordingUseCase
import ru.skatelab.capture.domain.usecase.StopRecordingUseCase
import ru.skatelab.capture.service.SensorRecordingService

@HiltViewModel
class RecordingViewModel
    @Inject
    constructor(
        private val cameraRepository: CameraRepository,
        private val bleRepository: BleRepository,
        private val imuCollector: ImuCollector,
        private val sessionRepository: SessionRepository,
        private val startRecordingUseCase: StartRecordingUseCase,
        private val stopRecordingUseCase: StopRecordingUseCase,
        private val readSensorInfoUseCase: ReadSensorInfoUseCase,
        private val timeSynchronizer: TimeSynchronizer,
        private val appLogger: Logger,
        @ApplicationContext private val appContext: Context,
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

        private val _reconnectingSensor = MutableStateFlow<SensorId?>(null)
        val reconnectingSensor: StateFlow<SensorId?> = _reconnectingSensor

        private val _sensorInfo = MutableStateFlow<Map<SensorId, SensorInfo?>>(emptyMap())
        val sensorInfo: StateFlow<Map<SensorId, SensorInfo?>> = _sensorInfo

        private val _elapsedMs = MutableStateFlow(0L)
        val elapsedMs: StateFlow<Long> = _elapsedMs

        private val _sessionId = MutableStateFlow<String?>(null)
        val sessionId: StateFlow<String?> = _sessionId

        val surfaceRequest: StateFlow<SurfaceRequest?> = cameraRepository.surfaceRequest

        private var currentStartInfo: RecordingStartInfo? = null
        private var batteryJob: kotlinx.coroutines.Job? = null
        private var currentCalibration = mapOf<SensorId, CalibrationData>()
        private var currentOutputDir: File? = null
        private var actualVideoFps: Int = 0
        private var fpsVerified: Boolean = false
        private var firstFrameNs: Long = 0L

        private var preparedVideoFile: File? = null
        private var preparedFramesFile: File? = null
        private var preparedImuLeftFile: File? = null
        private var preparedImuRightFile: File? = null
        private var reconnectJob: kotlinx.coroutines.Job? = null

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

        private suspend fun refreshBattery() {
            for (sensorId in listOf(SensorId.LEFT, SensorId.RIGHT)) {
                val result = readSensorInfoUseCase(sensorId)
                if (result.isSuccess) {
                    _sensorInfo.value = _sensorInfo.value + (sensorId to result.getOrThrow())
                }
            }
        }

        private fun stopReconnectWatch() {
            reconnectJob?.cancel()
            reconnectJob = null
            _reconnectingSensor.value = null
        }

        private var timerJob: kotlinx.coroutines.Job? = null
        private var recordingStartNanos: Long = 0L

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

        fun bindCamera(lifecycleOwner: LifecycleOwner, outputDir: File) {
            currentOutputDir = outputDir

            cleanupStaleCaptureDirs(outputDir.parentFile, excludeDir = outputDir)

            val timestamp = System.currentTimeMillis()
            preparedVideoFile = File(outputDir, "$timestamp.mp4")
            preparedFramesFile = File(outputDir, "${timestamp}_frames.csv")
            preparedImuLeftFile = File(outputDir, "${timestamp}_left.binpb")
            preparedImuRightFile = File(outputDir, "${timestamp}_right.binpb")

            viewModelScope.launch {
                cameraRepository.bindToLifecycle(lifecycleOwner)
                    .onSuccess {
                        _isPreviewReady.value = true
                        appLogger.i(TAG, "Camera bound to lifecycle")
                    }
                    .onFailure {
                        _error.value = "Camera prepare failed: ${it.message}"
                        appLogger.e(TAG, "Camera prepare failed: ${it.message}")
                    }
            }
        }

        /**
         * Remove stale capture directories that contain no .mp4 file (incomplete recordings).
         * Skips [excludeDir] to avoid deleting the active capture directory.
         */
        private fun cleanupStaleCaptureDirs(
            parentDir: File?,
            excludeDir: File,
        ) {
            if (parentDir == null || !parentDir.exists()) return

            parentDir.listFiles()
                ?.filter { it.isDirectory && it.name.startsWith("skatelab_capture_") && it != excludeDir }
                ?.forEach { dir ->
                    val hasVideo = dir.listFiles()?.any { it.extension == "mp4" } ?: false
                    if (!hasVideo) {
                        dir.deleteRecursively()
                        appLogger.i(TAG, "Cleaned up stale capture dir: ${dir.name}")
                    }
                }
        }

        fun startRecording(
            outputDir: File,
            calibration: Map<SensorId, CalibrationData>,
            context: Context,
        ) {
            currentCalibration = calibration
            currentOutputDir = outputDir

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

            if (!isPreviewReady.value) {
                _error.value = "Camera not prepared"
                return
            }

            startForegroundService(context)

            viewModelScope.launch {
                timeSynchronizer.sync(viewModelScope)
                timeSynchronizer.awaitSync()

                imuCollector.start(
                    viewModelScope,
                    mapOf(SensorId.LEFT to imuLeftFile, SensorId.RIGHT to imuRightFile),
                )

                startRecordingUseCase(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)
                    .onSuccess { startInfo ->
                        currentStartInfo = startInfo
                        _isRecording.value = true
                        startReconnectWatch()
                        startTimer()
                        appLogger.i(
                            TAG,
                            "Recording started: t0=${startInfo.t0Ns}, videoDelay=${startInfo.videoStartDelayMs}ms",
                        )
                    }
                    .onFailure {
                        imuCollector.stop()
                        stopForegroundService(context)
                        _error.value = "Recording start failed: ${it.message}"
                        appLogger.e(TAG, "Recording start failed: ${it.message}")
                    }
            }
        }

        fun stopRecording(context: Context) {
            val outputDir =
                currentOutputDir ?: run {
                    _error.value = "No active recording"
                    return
                }
            val startInfo =
                currentStartInfo ?: run {
                    _error.value = "No recording info"
                    return
                }

            viewModelScope.launch {
                timeSynchronizer.stop()
                stopReconnectWatch()
                stopTimer()

                stopRecordingUseCase()
                    .onSuccess { stopResult ->
                        actualVideoFps = stopResult.actualFps
                        fpsVerified = stopResult.fpsVerified
                        firstFrameNs = stopResult.firstFrameNs
                        appLogger.i(TAG, "Stopped: actualFps=${stopResult.actualFps} verified=${stopResult.fpsVerified} firstFrameNs=${stopResult.firstFrameNs}")
                    }
                    .onFailure {
                        appLogger.w(TAG, "Stop use case partial failure: ${it.message}")
                    }

                val imuCounts =
                    try {
                        imuCollector.stop()
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        appLogger.e(TAG, "IMU stop failed: ${e.message}")
                        null
                    }
                appLogger.i(TAG, "IMU samples: $imuCounts")

                _isRecording.value = false
                stopForegroundService(context)

                val clockOffsets =
                    mapOf(
                        SensorId.LEFT to timeSynchronizer.getOffset(SensorId.LEFT),
                        SensorId.RIGHT to timeSynchronizer.getOffset(SensorId.RIGHT),
                    )
                appLogger.i(TAG, "Clock offsets: $clockOffsets")

                val durationMs =
                    if (startInfo.t0Ns > 0) {
                        (System.nanoTime() - startInfo.t0Ns) / 1_000_000
                    } else {
                        0L
                    }

                val session =
                    CaptureSession(
                        id = UUID.randomUUID().toString(),
                        videoFile = startInfo.videoFile,
                        imuLeftFile = startInfo.imuLeftFile,
                        imuRightFile = startInfo.imuRightFile,
                        frameTimestampsFile = startInfo.framesFile,
                        manifestFile = File(outputDir, "manifest.json"),
                        t0Ns = startInfo.t0Ns,
                        durationMs = durationMs,
                        actualFps = actualVideoFps,
                        fpsVerified = fpsVerified,
                        firstFrameNs = if (startInfo.t0Ns > 0 && firstFrameNs > 0) firstFrameNs - startInfo.t0Ns else 0L,
                        timestampSource = startInfo.timestampSource,
                        videoStartDelayMs = startInfo.videoStartDelayMs,
                        imuStartDelayMs = startInfo.imuStartDelayMs,
                        calibration = currentCalibration,
                        clockOffsetNs = clockOffsets,
                        createdAt = System.currentTimeMillis(),
                        isComplete =
                            startInfo.videoFile.exists() &&
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

        private fun startForegroundService(context: Context) {
            val intent =
                Intent(context, SensorRecordingService::class.java).apply {
                    action = SensorRecordingService.ACTION_START
                }
            context.startForegroundService(intent)
            appLogger.i(TAG, "Foreground service started")
        }

        private fun stopForegroundService(context: Context) {
            val intent =
                Intent(context, SensorRecordingService::class.java).apply {
                    action = SensorRecordingService.ACTION_STOP
                }
            context.startService(intent)
            appLogger.i(TAG, "Foreground service stopped")
        }

        override fun onCleared() {
            super.onCleared()
            batteryJob?.cancel()
            timeSynchronizer.stop()
            runBlocking(Dispatchers.IO) {
                try {
                    imuCollector.stop()
                } catch (e: Exception) {
                    appLogger.e(TAG, "onCleared IMU stop failed: ${e.message}")
                }
                try {
                    stopForegroundService(appContext)
                } catch (e: Exception) {
                    appLogger.e(TAG, "onCleared service stop failed: ${e.message}")
                }
                currentOutputDir?.let { dir ->
                    val hasVideo = dir.listFiles()?.any { it.extension == "mp4" } ?: false
                    if (!hasVideo && dir.exists()) {
                        dir.deleteRecursively()
                        appLogger.i(TAG, "Cleaned up incomplete capture dir on clear: ${dir.name}")
                    }
                }
                try {
                    cameraRepository.release()
                } catch (e: Exception) {
                    appLogger.e(TAG, "onCleared camera release failed: ${e.message}")
                }
            }
        }
    }
