package ru.skatelab.capture.data.camera

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.MediaRecorder
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.Range
import android.view.Surface
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeout
import ru.skatelab.capture.domain.repository.CameraRepository
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class Camera2Recorder(
    private val context: Context,
) {
    private var cameraManager: CameraManager? = null
    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var mediaRecorder: MediaRecorder? = null
    private var timestampTracker: FrameTimestampTracker? = null
    private var timestampsFile: File? = null
    private var previewSurface: Surface? = null
    private var callbackHandler: Handler? = null
    private var handlerThread: HandlerThread? = null

    private var cameraId: String? = null
    private var tStartCalledNs: Long = 0L
    private var targetFps: Int = 60

    @Volatile
    private var isRecording = false

    @SuppressLint("MissingPermission")
    suspend fun openCamera(): String {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        cameraManager = manager

        cameraId = manager.cameraIdList.firstOrNull { id ->
            manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        } ?: throw IllegalStateException("No back camera found")

        handlerThread = HandlerThread("Camera2Callback").apply { start() }
        callbackHandler = Handler(handlerThread!!.looper)

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

    fun getAvailableFpsRanges(): List<Range<Int>> {
        val chars = cameraManager?.getCameraCharacteristics(cameraId!!) ?: return emptyList()
        return chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)?.toList() ?: emptyList()
    }

    @SuppressLint("MissingPermission")
    suspend fun prepare(
        outputFile: File,
        timestampsFile: File,
        previewSurface: Surface?,
        width: Int = 1920,
        height: Int = 1080,
        fps: Int = 60,
    ) {
        val manager = cameraManager ?: throw IllegalStateException("Camera not opened")
        this.timestampsFile = timestampsFile
        this.targetFps = fps
        timestampTracker = FrameTimestampTracker()

        mediaRecorder = MediaRecorder(context).apply {
            setVideoSource(MediaRecorder.VideoSource.SURFACE)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setOutputFile(outputFile.absolutePath)
            setVideoEncodingBitRate(8_000_000)
            setVideoFrameRate(fps)
            setVideoSize(width, height)
            setVideoEncoder(MediaRecorder.VideoEncoder.H264)
            prepare()
        }

        this.previewSurface = previewSurface

        cameraDevice = suspendCancellableCoroutine { cont ->
            manager.openCamera(cameraId!!, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) { cont.resume(camera) }
                override fun onDisconnected(camera: CameraDevice) {
                    cont.resumeWithException(Exception("Camera disconnected"))
                }
                override fun onError(camera: CameraDevice, error: Int) {
                    cont.resumeWithException(Exception("Camera error $error"))
                }
            }, callbackHandler)
        }

        // Start preview-only session so the SurfaceView shows camera feed immediately
        startPreview()
    }

    /**
     * Create a preview-only capture session (suspend).
     * Used in prepare() and when surface is recreated.
     */
    suspend fun startPreview(surface: Surface? = previewSurface) {
        val device = cameraDevice ?: return
        val s = surface ?: return

        // Close any existing session first
        captureSession?.close()
        captureSession = null

        captureSession = suspendCancellableCoroutine { cont ->
            device.createCaptureSession(listOf(s), object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) { cont.resume(session) }
                override fun onConfigureFailed(session: CameraCaptureSession) {
                    cont.resumeWithException(Exception("Preview session config failed"))
                }
            }, callbackHandler)
        }

        val builder = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
        builder.addTarget(s)
        captureSession!!.setRepeatingRequest(builder.build(), null, callbackHandler)
        this.previewSurface = surface
    }

    /**
     * Create a preview-only capture session (blocking, best-effort).
     * Used after stopRecording() to restore camera preview.
     */
    private fun startPreviewBlocking() {
        val device = cameraDevice ?: return
        val surface = previewSurface ?: return
        val handler = callbackHandler ?: return

        device.createCaptureSession(listOf(surface), object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(session: CameraCaptureSession) {
                try {
                    val builder = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                    builder.addTarget(surface)
                    session.setRepeatingRequest(builder.build(), null, handler)
                    captureSession = session
                } catch (_: Exception) { }
            }
            override fun onConfigureFailed(session: CameraCaptureSession) { }
        }, handler)
    }

    @SuppressLint("MissingPermission")
    suspend fun startRecording(): CameraRepository.RecordingStartResult {
        if (isRecording) throw IllegalStateException("Recording already in progress")
        isRecording = true

        val device = cameraDevice ?: throw IllegalStateException("Camera not prepared")
        val recorder = mediaRecorder ?: throw IllegalStateException("MediaRecorder not prepared")

        // Close preview session before creating recording session
        // (Camera2 forbids two concurrent sessions on the same device)
        captureSession?.close()
        captureSession = null

        timestampTracker?.open(timestampsFile!!)

        val surfaces = mutableListOf<Surface>()
        val recorderSurface = recorder.surface
        surfaces.add(recorderSurface)
        if (previewSurface != null) {
            surfaces.add(previewSurface!!)
        }

        captureSession = suspendCancellableCoroutine { cont ->
            device.createCaptureSession(surfaces, object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) { cont.resume(session) }
                override fun onConfigureFailed(session: CameraCaptureSession) {
                    cont.resumeWithException(Exception("Session config failed"))
                }
            }, callbackHandler)
        }

        tStartCalledNs = SystemClock.elapsedRealtimeNanos()
        recorder.start()

        val builder = captureSession!!.device.createCaptureRequest(CameraDevice.TEMPLATE_RECORD)
        builder.addTarget(recorderSurface)
        if (previewSurface != null && surfaces.contains(previewSurface)) {
            builder.addTarget(previewSurface!!)
        }

        val fpsRange = Range(targetFps, targetFps)
        builder.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, fpsRange)

        builder.set(CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE,
            CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE_OFF)

        val chars = cameraManager?.getCameraCharacteristics(cameraId!!)
        if (chars?.get(CameraCharacteristics.LENS_INFO_AVAILABLE_OPTICAL_STABILIZATION)
                ?.contains(CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_OFF) == true) {
            builder.set(CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE,
                CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_OFF)
        }

        val firstFrameDeferred = CompletableDeferred<Long>()

        captureSession!!.setRepeatingRequest(builder.build(), object : CameraCaptureSession.CaptureCallback() {
            override fun onCaptureStarted(
                session: CameraCaptureSession,
                request: CaptureRequest,
                timestamp: Long,
                frameNumber: Long,
            ) {
                timestampTracker?.onFrame(timestamp)
                if (!firstFrameDeferred.isCompleted) {
                    firstFrameDeferred.complete(timestamp)
                }
            }
        }, callbackHandler)

        val tFirstFrameNs = try {
            withTimeout(2_000L) { firstFrameDeferred.await() }
        } catch (_: Exception) {
            throw IllegalStateException("No first frame received within 2s")
        }

        val videoStartDelayMs = (tFirstFrameNs - tStartCalledNs) / 1_000_000

        return CameraRepository.RecordingStartResult(
            tStartCalledNs = tStartCalledNs,
            tFirstFrameNs = tFirstFrameNs,
            timestampSource = getTimestampSource(),
            videoStartDelayMs = videoStartDelayMs,
        )
    }

    fun stopRecording(): CameraRepository.RecordingStopResult {
        isRecording = false
        captureSession?.stopRepeating()
        captureSession?.close()
        captureSession = null
        mediaRecorder?.stop()
        timestampTracker?.close()

        // Re-create preview-only session so camera stays visible after recording stops
        startPreviewBlocking()

        return CameraRepository.RecordingStopResult(
            actualFps = 0,
            fpsVerified = false,
        )
    }

    /**
     * Close the current capture session (preview or recording).
     * Called when the preview surface is destroyed.
     */
    fun closeSession() {
        captureSession?.stopRepeating()
        captureSession?.close()
        captureSession = null
    }

    fun release() {
        isRecording = false
        captureSession?.close()
        cameraDevice?.close()
        mediaRecorder?.release()
        handlerThread?.quitSafely()
        cameraDevice = null
        mediaRecorder = null
        captureSession = null
        handlerThread = null
        callbackHandler = null
    }
}
