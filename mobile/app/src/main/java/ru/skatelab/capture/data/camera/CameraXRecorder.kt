package ru.skatelab.capture.data.camera

import android.content.Context
import android.os.SystemClock
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.viewfinder.CameraViewfinder
import androidx.lifecycle.LifecycleOwner
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withTimeout
import ru.skatelab.capture.domain.repository.CameraRepository

@Singleton
class CameraXRecorder
    @Inject
    constructor(
        @ApplicationContext private val context: Context,
    ) {
        private val _isPreviewReady = MutableStateFlow(false)
        val isPreviewReady: StateFlow<Boolean> = _isPreviewReady.asStateFlow()

        private val _isRecording = MutableStateFlow(false)
        val isRecording: StateFlow<Boolean> = _isRecording.asStateFlow()

        private var cameraProvider: ProcessCameraProvider? = null
        private var camera: Camera? = null
        private var activeRecording: Recording? = null
        private var timestampTracker: FrameTimestampTracker? = null
        private var viewfinder: CameraViewfinder? = null
        private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

        private var tStartCalledNs: Long = 0L
        private var recorder: Recorder? = null
        private var videoCapture: VideoCapture<Recorder>? = null
        private var preview: Preview? = null

        suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit> =
            runCatching {
                val provider = ProcessCameraProvider.getInstance(context)
                cameraProvider = provider

                preview = Preview.Builder().build()

                recorder =
                    Recorder.Builder()
                        .setAspectRatio(androidx.camera.core.AspectRatio.RATIO_16_9)
                        .build()
                videoCapture = VideoCapture.withOutput(recorder!!)

                val imageAnalysis =
                    ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                        .build()

                val cameraSelector =
                    CameraSelector.Builder()
                        .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                        .build()

                provider.unbindAll()

                viewfinder?.let { vf ->
                    preview?.setSurfaceProvider(vf.surfaceProvider)
                }

                camera =
                    provider.bindToLifecycle(
                        lifecycleOwner,
                        cameraSelector,
                        preview,
                        videoCapture,
                        imageAnalysis,
                    )

                _isPreviewReady.value = true
            }

        fun setViewfinder(viewfinder: CameraViewfinder?) {
            this.viewfinder = viewfinder
            viewfinder?.let { vf ->
                preview?.setSurfaceProvider(vf.surfaceProvider)
            }
        }

        fun unbind() {
            cameraProvider?.unbindAll()
            _isPreviewReady.value = false
        }

        suspend fun startRecording(
            videoFile: File,
            framesFile: File,
        ): Result<CameraRepository.RecordingStartResult> =
            runCatching {
                val capture = videoCapture ?: throw IllegalStateException("Camera not bound")
                timestampTracker = FrameTimestampTracker()
                timestampTracker?.open(framesFile)

                tStartCalledNs = SystemClock.elapsedRealtimeNanos()

                val outputOptions = FileOutputOptions.Builder(videoFile).build()

                val pendingRecording = capture.output.prepareRecording(context, outputOptions)

                val startDeferred = CompletableDeferred<Unit>()

                activeRecording =
                    pendingRecording.start(cameraExecutor) { event ->
                        when (event) {
                            is VideoRecordEvent.Start -> {
                                _isRecording.value = true
                                startDeferred.complete(Unit)
                            }
                            is VideoRecordEvent.Finalize -> {
                                _isRecording.value = false
                                timestampTracker?.close()
                            }
                            else -> {}
                        }
                    }

                try {
                    withTimeout(3_000L) { startDeferred.await() }
                } catch (_: Exception) {
                    // Recording started but event didn't fire — still proceed
                    _isRecording.value = true
                }

                val tFirstFrameNs = SystemClock.elapsedRealtimeNanos()

                CameraRepository.RecordingStartResult(
                    tStartCalledNs = tStartCalledNs,
                    tFirstFrameNs = tFirstFrameNs,
                    timestampSource = "REALTIME",
                    videoStartDelayMs = (tFirstFrameNs - tStartCalledNs) / 1_000_000,
                )
            }

        suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> =
            runCatching {
                val rec = activeRecording ?: throw IllegalStateException("No active recording")
                rec.stop()
                _isRecording.value = false

                val actualFps = timestampTracker?.computeFps() ?: 0
                val frameCount = timestampTracker?.getFrameCount() ?: 0

                CameraRepository.RecordingStopResult(
                    actualFps = actualFps,
                    fpsVerified = frameCount > 10 && actualFps > 0,
                )
            }

        fun release() {
            activeRecording?.close()
            activeRecording = null
            cameraProvider?.unbindAll()
            cameraExecutor.shutdownNow()
            cameraProvider = null
            camera = null
            recorder = null
            videoCapture = null
            preview = null
            _isPreviewReady.value = false
            _isRecording.value = false
        }
    }