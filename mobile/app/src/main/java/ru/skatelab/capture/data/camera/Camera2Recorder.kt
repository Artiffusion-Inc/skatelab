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
import kotlinx.coroutines.suspendCancellableCoroutine
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
    }

    @SuppressLint("MissingPermission")
    suspend fun startRecording(): CameraRepository.RecordingStartResult {
        val device = cameraDevice ?: throw IllegalStateException("Camera not prepared")
        val recorder = mediaRecorder ?: throw IllegalStateException("MediaRecorder not prepared")

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

        var firstFrameCaptured = false
        var tFirstFrameNs = 0L

        captureSession!!.setRepeatingRequest(builder.build(), object : CameraCaptureSession.CaptureCallback() {
            override fun onCaptureStarted(
                session: CameraCaptureSession,
                request: CaptureRequest,
                timestamp: Long,
                frameNumber: Long,
            ) {
                // Record every frame timestamp via tracker
                timestampTracker?.onFrame(timestamp)
                if (!firstFrameCaptured) {
                    firstFrameCaptured = true
                    tFirstFrameNs = timestamp
                }
            }
        }, callbackHandler)

        // Wait briefly for first frame timestamp
        val deadline = SystemClock.elapsedRealtimeNanos() + 2_000_000_000L // 2s timeout
        while (!firstFrameCaptured && SystemClock.elapsedRealtimeNanos() < deadline) {
            Thread.sleep(10L)
        }
        if (!firstFrameCaptured) {
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
        captureSession?.stopRepeating()
        captureSession?.close()
        mediaRecorder?.stop()
        timestampTracker?.close()
        return CameraRepository.RecordingStopResult(
            actualFps = 0,
            fpsVerified = false,
        )
    }

    fun release() {
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
