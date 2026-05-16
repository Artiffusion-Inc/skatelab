package ru.skatelab.capture.domain.service

import java.io.File
import ru.skatelab.capture.domain.model.CaptureSession

interface SessionExporter {
    suspend fun export(
        session: CaptureSession,
        zipFile: File,
    )
}

interface ManifestWriter {
    fun version(v: String): ManifestWriter

    fun t0Ns(ns: Long): ManifestWriter

    fun durationMs(ms: Long): ManifestWriter

    fun video(block: VideoBlock.() -> Unit): ManifestWriter

    fun imu(
        side: String,
        block: ImuBlock.() -> Unit,
    ): ManifestWriter

    fun calibration(block: CalibrationBlock.() -> Unit): ManifestWriter

    fun createdAt(iso: String): ManifestWriter

    fun build(): String

    interface VideoBlock {
        fun filename(f: String)

        fun fps(f: Int)

        fun width(w: Int)

        fun height(h: Int)

        fun actualFpsVerified(v: Boolean)

        fun timestampSource(s: String)

        fun videoStartDelayMs(ms: Long)

        fun frameTimestampsFile(f: String)

        fun firstFrameNs(ns: Long)
    }

    interface ImuBlock {
        fun filename(f: String)

        fun format(f: String)

        fun sampleRateHz(hz: Int)

        fun sensorId(id: String)

        fun clockOffsetNs(ns: Long)

        fun imuStartDelayMs(ms: Long)

        fun resyncIntervalsS(s: Int)

        fun reconnectCount(c: Int)

        fun droppedPartialCount(c: Int)
    }

    interface CalibrationBlock {
        fun left(
            quatRef: FloatArray,
            calibratedAt: String,
        )

        fun right(
            quatRef: FloatArray,
            calibratedAt: String,
        )
    }
}
