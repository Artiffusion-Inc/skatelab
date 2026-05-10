package ru.skatelab.capture.data.camera

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.SystemClock
import androidx.camera.core.CameraSelector
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.VideoCapture
import androidx.core.content.ContextCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.coroutines.resume

class CameraXRecorder(
    private val context: Context,
) {
    private var cameraProvider: ProcessCameraProvider? = null
    private var recorder: Recorder? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var recording: androidx.camera.video.Recording? = null

    private var cameraManager: CameraManager? = null
    private var cameraId: String? = null

    private var outputFile: File? = null
    private var timestampsFile: File? = null
    private var targetFps: Int = 60
    private var tStartCalledNs: Long = 0L
    private var tFirstFrameNs: Long = 0L

    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    @SuppressLint("MissingPermission")
    suspend fun openCamera(): String {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        cameraManager = manager

        cameraId = manager.cameraIdList.firstOrNull { id ->
            manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        } ?: throw IllegalStateException("No back camera found")

        return cameraId!!
    }

    fun getHardwareLevel(): Int {
        val chars = cameraManager?.getCameraCharacteristics(cameraId!!) ?: return -1
        return chars.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL) ?: -1
    }

    fun getTimestampSource(): String {
        val chars = cameraManager?.getCameraCharacteristics(cameraId!!) ?: return "UNKNOWN"
        val source = chars.get(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE) ?: 0
        return if (source == CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME) "REALTIME" else "UNKNOWN"
    }

    suspend fun prepare(
        outputFile: File,
        timestampsFile: File,
        previewSurface: Any?,
        width: Int = 1920,
        height: Int = 1080,
        fps: Int = 60,
    ) {
        this.outputFile = outputFile
        this.timestampsFile = timestampsFile
        this.targetFps = fps

        cameraProvider = suspendCancellableCoroutine { cont ->
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener(
                { cont.resume(future.get()) },
                ContextCompat.getMainExecutor(context),
            )
        }

        recorder = Recorder.Builder()
            .setQualitySelector(QualitySelector.from(Quality.HIGHEST))
            .build()
        videoCapture = VideoCapture.withOutput(recorder!!)
    }

    @SuppressLint("MissingPermission", "RestrictedApi")
    suspend fun startRecording(): CameraRepository.RecordingStartResult {
        val provider = cameraProvider ?: throw IllegalStateException("Camera not prepared")
        val capture = videoCapture ?: throw IllegalStateException("VideoCapture not prepared")
        val vidFile = outputFile ?: throw IllegalStateException("Output file not set")
        val tsFile = timestampsFile ?: throw IllegalStateException("Timestamps file not set")

        val cameraSelector = CameraSelector.Builder()
            .requireLensFacing(CameraSelector.LENS_FACING_BACK)
            .build()

        provider.unbindAll()
        provider.bindToLifecycle(StubLifecycleOwner, cameraSelector, capture)

        tStartCalledNs = SystemClock.elapsedRealtimeNanos()

        val outputOptions = FileOutputOptions.Builder(vidFile).build()
        recording = capture.output
            .prepareRecording(context, outputOptions)
            .start(cameraExecutor) { /* event listener stub */ }

        val frameIntervalNs = 1_000_000_000L / targetFps
        tFirstFrameNs = tStartCalledNs + frameIntervalNs

        writeEstimatedTimestamps(tsFile)

        return CameraRepository.RecordingStartResult(
            tStartCalledNs = tStartCalledNs,
            tFirstFrameNs = tFirstFrameNs,
            timestampSource = "CAMERAX_ESTIMATED",
            videoStartDelayMs = (tFirstFrameNs - tStartCalledNs) / 1_000_000,
        )
    }

    fun stopRecording(): CameraRepository.RecordingStopResult {
        recording?.close()
        recording = null
        return CameraRepository.RecordingStopResult(
            actualFps = targetFps,
            fpsVerified = false,
        )
    }

    fun release() {
        recording = null
        cameraProvider?.unbindAll()
        cameraProvider = null
        recorder = null
        videoCapture = null
        cameraExecutor.shutdownNow()
    }

    private fun writeEstimatedTimestamps(file: File) {
        val frameIntervalNs = 1_000_000_000L / targetFps
        val estimatedFrameCount = targetFps * 10
        file.bufferedWriter().use { writer ->
            writer.write("frame_index,timestamp_ns\n")
            for (i in 0 until estimatedFrameCount) {
                writer.write("$i,${tFirstFrameNs + i * frameIntervalNs}\n")
            }
        }
    }

    private object StubLifecycleOwner : androidx.lifecycle.LifecycleOwner {
        private val lifecycleRegistry = androidx.lifecycle.LifecycleRegistry(this).apply {
            currentState = androidx.lifecycle.Lifecycle.State.RESUMED
        }
        override val lifecycle: androidx.lifecycle.Lifecycle = lifecycleRegistry
    }
}
