package ru.skatelab.capture.data.camera

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.view.Surface
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

@Singleton
class Camera2Recorder @Inject constructor(
    @ApplicationContext private val context: Context,
) : CameraRepository {

    private val _isRecording = MutableStateFlow(false)
    private val _frameTimestamps = MutableStateFlow(0L)
    private val _currentFps = MutableStateFlow(0)
    private val _hardwareLevel = MutableStateFlow(0)

    override val isRecording: Flow<Boolean> = _isRecording
    override val frameTimestamps: Flow<Long> = _frameTimestamps
    override val currentFps: Flow<Int> = _currentFps
    override val hardwareLevel: Flow<Int> = _hardwareLevel

    private var cameraManager: CameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var mediaRecorder: MediaRecorder? = null
    private var imageReader: ImageReader? = null
    private var cameraHandler: Handler? = null
    private var cameraThread: HandlerThread? = null

    private var outputFile: File? = null
    private var timestampsFile: File? = null
    private var frameTracker: FrameTimestampTracker? = null

    @SuppressLint("MissingPermission")
    override suspend fun prepare(outputFile: File, timestampsFile: File): Result<Unit> = runCatching {
        this.outputFile = outputFile
        this.timestampsFile = timestampsFile

        // Find back camera with best capability
        val cameraId = findBackCamera() ?: throw IllegalStateException("No back camera found")

        val characteristics = cameraManager.getCameraCharacteristics(cameraId)
        _hardwareLevel.value = characteristics.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL) ?: 0

        // Start camera handler thread
        cameraThread = HandlerThread("camera2-handler").apply { start() }
        cameraHandler = Handler(cameraThread!!.looper)

        // Open camera
        cameraDevice = openCamera(cameraId)

        // Setup frame timestamp tracker
        frameTracker = FrameTimestampTracker()
        frameTracker!!.open(timestampsFile)
    }

    @SuppressLint("MissingPermission")
    override suspend fun startRecording(): Result<CameraRepository.RecordingStartResult> = runCatching {
        val device = cameraDevice ?: throw IllegalStateException("Camera not prepared")
        val out = outputFile ?: throw IllegalStateException("Output file not set")

        val t0 = SystemClock.elapsedRealtimeNanos()

        // Setup MediaRecorder
        mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }

        mediaRecorder!!.apply {
            setVideoSource(MediaRecorder.VideoSource.SURFACE)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setOutputFile(out.absolutePath)
            setVideoEncodingBitRate(20_000_000) // 20 Mbps
            setVideoFrameRate(60)
            setVideoSize(1920, 1080)
            setVideoEncoder(MediaRecorder.VideoEncoder.H264)
            prepare()
        }

        // Setup ImageReader for frame timestamps
        imageReader = ImageReader.newInstance(1920, 1080, android.graphics.ImageFormat.YUV_420_888, 2)
        imageReader!!.setOnImageAvailableListener({ reader ->
            val image = reader.acquireLatestImage() ?: return@setOnImageAvailableListener
            val timestamp = image.timestamp
            frameTracker?.onFrame(timestamp)
            _frameTimestamps.value = timestamp
            image.close()
        }, cameraHandler)

        // Create capture session with both surfaces
        val surfaces = listOf(mediaRecorder!!.surface, imageReader!!.surface)
        captureSession = createCaptureSession(device, surfaces)

        // Start recording
        mediaRecorder!!.start()
        _isRecording.value = true

        val tFirstFrameNs = frameTracker?.getFirstFrameNs() ?: t0

        CameraRepository.RecordingStartResult(
            tStartCalledNs = t0,
            tFirstFrameNs = tFirstFrameNs,
            timestampSource = "camera2",
            videoStartDelayMs = (tFirstFrameNs - t0) / 1_000_000,
        )
    }

    override suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> = runCatching {
        try {
            mediaRecorder?.stop()
        } catch (_: Exception) { }

        captureSession?.close()
        captureSession = null
        _isRecording.value = false

        val fps = frameTracker?.computeFps() ?: 0
        _currentFps.value = fps

        CameraRepository.RecordingStopResult(
            actualFps = fps,
            fpsVerified = fps in 55..65,
        )
    }

    override suspend fun release() {
        try {
            mediaRecorder?.release()
        } catch (_: Exception) { }
        imageReader?.close()
        cameraDevice?.close()
        cameraThread?.quitSafely()
        frameTracker?.close()

        mediaRecorder = null
        imageReader = null
        cameraDevice = null
        cameraThread = null
        captureSession = null
        _isRecording.value = false
    }

    @SuppressLint("MissingPermission")
    private suspend fun openCamera(cameraId: String): CameraDevice = suspendCancellableCoroutine { cont ->
        cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
            override fun onOpened(camera: CameraDevice) { cont.resume(camera) }
            override fun onDisconnected(camera: CameraDevice) { camera.close(); cont.resumeWithException(IllegalStateException("Camera disconnected")) }
            override fun onError(camera: CameraDevice, error: Int) { camera.close(); cont.resumeWithException(IllegalStateException("Camera error: $error")) }
        }, cameraHandler)
    }

    private suspend fun createCaptureSession(device: CameraDevice, surfaces: List<Surface>): CameraCaptureSession = suspendCancellableCoroutine { cont ->
        device.createCaptureSession(surfaces, object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(session: CameraCaptureSession) {
                // Start repeating request for preview+recording
                val request = device.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
                    surfaces.forEach { addTarget(it) }
                }
                session.setRepeatingRequest(request.build(), null, cameraHandler)
                cont.resume(session)
            }
            override fun onConfigureFailed(session: CameraCaptureSession) { cont.resumeWithException(IllegalStateException("Capture session config failed")) }
        }, cameraHandler)
    }

    private fun findBackCamera(): String? {
        return cameraManager.cameraIdList.firstOrNull { id ->
            val chars = cameraManager.getCameraCharacteristics(id)
            chars.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        }
    }
}
