package ru.skatelab.capture.domain.model

import java.io.File

data class CaptureSession(
    val id: String,
    val videoFile: File,
    val imuLeftFile: File,
    val imuRightFile: File,
    val frameTimestampsFile: File,
    val manifestFile: File,
    val t0Ns: Long,
    val durationMs: Long,
    val actualFps: Int,
    val fpsVerified: Boolean,
    val firstFrameNs: Long,
    val videoWidth: Int = 0,
    val videoHeight: Int = 0,
    val timestampSource: String,
    val videoStartDelayMs: Long,
    val imuStartDelayMs: Map<SensorId, Long>,
    val calibration: Map<SensorId, CalibrationData>,
    val clockOffsetNs: Map<SensorId, Long> = emptyMap(),
    val createdAt: Long,
    val isComplete: Boolean,
)
