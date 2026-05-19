package ru.skatelab.capture.data.camera

import android.content.Context
import android.media.MediaMetadataRetriever
import android.os.SystemClock
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.SurfaceRequest
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
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
import kotlinx.coroutines.guava.await
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import ru.skatelab.capture.domain.repository.CameraRepository

internal data class VideoMetadata(val width: Int, val height: Int, val bitrate: Long)

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

        private val _surfaceRequest = MutableStateFlow<SurfaceRequest?>(null)
        val surfaceRequest: StateFlow<SurfaceRequest?> = _surfaceRequest.asStateFlow()

        private val _videoMetadata = MutableStateFlow<VideoMetadata?>(null)
        internal val videoMetadata: StateFlow<VideoMetadata?> = _videoMetadata.asStateFlow()

        private val _recordingError = MutableStateFlow<String?>(null)
        val recordingError: StateFlow<String?> = _recordingError.asStateFlow()

        private var cameraProvider: ProcessCameraProvider? = null
        private var camera: Camera? = null
        private var activeRecording: Recording? = null
        private var timestampTracker: FrameTimestampTracker? = null
        private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

        private var tStartCalledNs: Long = 0L
        private var recorder: Recorder? = null
        private var videoCapture: VideoCapture<Recorder>? = null
        private var preview: Preview? = null
        private var finalizeDeferred: CompletableDeferred<VideoMetadata?>? = null

        suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit> =
            runCatching {
                if (cameraExecutor.isShutdown) {
                    cameraExecutor = Executors.newSingleThreadExecutor()
                }

                val provider = ProcessCameraProvider.getInstance(context).await()
                cameraProvider = provider

                val p =
                    Preview.Builder().build().also { preview ->
                        preview.setSurfaceProvider(cameraExecutor) { request ->
                            _surfaceRequest.value = request
                        }
                    }
                preview = p

                val r =
                    Recorder.Builder()
                        .setAspectRatio(androidx.camera.core.AspectRatio.RATIO_16_9)
                        .setQualitySelector(
                            QualitySelector.fromOrderedList(
                                listOf(Quality.HD, Quality.SD),
                                FallbackStrategy.lowerQualityOrHigherThan(Quality.SD),
                            ),
                        )
                        .build()
                recorder = r
                val vc = VideoCapture.withOutput(r)
                videoCapture = vc

                val imageAnalysis =
                    ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                        .build()
                imageAnalysis.setAnalyzer(cameraExecutor) { image ->
                    timestampTracker?.onFrame(SystemClock.elapsedRealtimeNanos())
                    image.close()
                }

                val cameraSelector =
                    CameraSelector.Builder()
                        .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                        .build()

                provider.unbindAll()

                camera =
                    provider.bindToLifecycle(
                        lifecycleOwner,
                        cameraSelector,
                        p,
                        vc,
                        imageAnalysis,
                    )

                _isPreviewReady.value = true
            }

        fun unbind() {
            cameraProvider?.unbindAll()
            _surfaceRequest.value = null
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
                finalizeDeferred = CompletableDeferred()

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
                                if (event.hasError()) {
                                    _recordingError.value = "Video recording error: ${event.error}"
                                }
                                val meta = extractVideoMetadata(videoFile)
                                _videoMetadata.value = meta
                                finalizeDeferred?.complete(meta)
                            }
                            else -> {}
                        }
                    }

                try {
                    withTimeout(3_000L) { startDeferred.await() }
                } catch (_: Exception) {
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

                val meta = withTimeoutOrNull(3_000L) { finalizeDeferred?.await() }
                finalizeDeferred = null

                val actualFps = timestampTracker?.computeFps() ?: 0
                val frameCount = timestampTracker?.getFrameCount() ?: 0
                val firstFrameNs = timestampTracker?.getFirstFrameNs() ?: 0L

                CameraRepository.RecordingStopResult(
                    actualFps = actualFps,
                    fpsVerified = frameCount > 10 && actualFps > 0,
                    firstFrameNs = firstFrameNs,
                    actualWidth = meta?.width ?: 0,
                    actualHeight = meta?.height ?: 0,
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
            _surfaceRequest.value = null
            _isPreviewReady.value = false
            _isRecording.value = false
        }

        private fun extractVideoMetadata(videoFile: File): VideoMetadata? {
            val retriever = MediaMetadataRetriever()
            return try {
                retriever.setDataSource(videoFile.absolutePath)
                VideoMetadata(
                    width = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0,
                    height = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0,
                    bitrate = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toLongOrNull() ?: 0L,
                )
            } catch (_: Exception) {
                null
            } finally {
                try {
                    retriever.release()
                } catch (_: Exception) {
                }
            }
        }
    }
