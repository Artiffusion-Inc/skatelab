package ru.skatelab.capture.data.export

import org.json.JSONArray
import org.json.JSONObject
import javax.inject.Inject

/**
 * Fluent builder for JSON manifest v2.0.
 * Produces the manifest.json file included in the capture ZIP export.
 */
class ManifestBuilder @Inject constructor() {

    private var version: String = "2.0"
    private var t0Ns: Long = 0L
    private var durationMs: Long = 0L
    private var video: JSONObject? = null
    private var imuLeft: JSONObject? = null
    private var imuRight: JSONObject? = null
    private var calibration: JSONObject? = null
    private var createdAt: String = ""

    fun version(v: String): ManifestBuilder = apply { this.version = v }

    fun t0Ns(ns: Long): ManifestBuilder = apply { this.t0Ns = ns }

    fun durationMs(ms: Long): ManifestBuilder = apply { this.durationMs = ms }

    fun video(block: VideoBuilder.() -> Unit): ManifestBuilder = apply {
        video = VideoBuilder().apply(block).build()
    }

    fun imu(side: String, block: ImuEntryBuilder.() -> Unit): ManifestBuilder = apply {
        val entry = ImuEntryBuilder().apply(block).build()
        when (side.lowercase()) {
            "left" -> imuLeft = entry
            "right" -> imuRight = entry
        }
    }

    fun calibration(block: CalibrationBuilder.() -> Unit): ManifestBuilder = apply {
        calibration = CalibrationBuilder().apply(block).build()
    }

    fun createdAt(iso: String): ManifestBuilder = apply { this.createdAt = iso }

    /** Build the manifest as a JSON string. */
    fun build(): String {
        val root = JSONObject().apply {
            put("version", version)
            put("created_at", createdAt)
            put("t0_ns", t0Ns)
            put("duration_ms", durationMs)
            video?.let { put("video", it) }
            val imuObj = JSONObject().apply {
                imuLeft?.let { put("left", it) }
                imuRight?.let { put("right", it) }
            }
            put("imu", imuObj)
            calibration?.let { put("calibration", it) }
        }
        return root.toString(2)
    }

    class VideoBuilder {
        private var filename: String = ""
        private var fps: Int = 60
        private var width: Int = 1920
        private var height: Int = 1080
        private var actualFpsVerified: Boolean = false
        private var frameTimestampsFile: String = ""
        private var timestampSource: String = "UNKNOWN"
        private var videoStartDelayMs: Long = 0L
        private var firstFrameNs: Long = 0L

        fun filename(f: String) = apply { this.filename = f }
        fun fps(f: Int) = apply { this.fps = f }
        fun width(w: Int) = apply { this.width = w }
        fun height(h: Int) = apply { this.height = h }
        fun actualFpsVerified(v: Boolean) = apply { this.actualFpsVerified = v }
        fun frameTimestampsFile(f: String) = apply { this.frameTimestampsFile = f }
        fun timestampSource(s: String) = apply { this.timestampSource = s }
        fun videoStartDelayMs(ms: Long) = apply { this.videoStartDelayMs = ms }
        fun firstFrameNs(ns: Long) = apply { this.firstFrameNs = ns }

        fun build() = JSONObject().apply {
            put("filename", filename)
            put("fps", fps)
            put("width", width)
            put("height", height)
            put("actual_fps_verified", actualFpsVerified)
            put("frame_timestamps_file", frameTimestampsFile)
            put("timestamp_source", timestampSource)
            put("video_start_delay_ms", videoStartDelayMs)
            put("first_frame_ns", firstFrameNs)
        }
    }

    class ImuEntryBuilder {
        private var filename: String = ""
        private var format: String = "delimited_imu_record"
        private var sampleRateHz: Int = 100
        private var sensorId: String = ""
        private var clockOffsetNs: Long = 0L
        private var imuStartDelayMs: Long = 0L
        private var resyncIntervalsS: Int = 30
        private var reconnectCount: Int = 0
        private var droppedPartialCount: Int = 0

        fun filename(f: String) = apply { this.filename = f }
        fun format(f: String) = apply { this.format = f }
        fun sampleRateHz(hz: Int) = apply { this.sampleRateHz = hz }
        fun sensorId(id: String) = apply { this.sensorId = id }
        fun clockOffsetNs(ns: Long) = apply { this.clockOffsetNs = ns }
        fun imuStartDelayMs(ms: Long) = apply { this.imuStartDelayMs = ms }
        fun resyncIntervalsS(s: Int) = apply { this.resyncIntervalsS = s }
        fun reconnectCount(c: Int) = apply { this.reconnectCount = c }
        fun droppedPartialCount(c: Int) = apply { this.droppedPartialCount = c }

        fun build() = JSONObject().apply {
            put("filename", filename)
            put("format", format)
            put("sample_rate_hz", sampleRateHz)
            put("sensor_id", sensorId)
            put("clock_offset_ns", clockOffsetNs)
            put("imu_start_delay_ms", imuStartDelayMs)
            put("resync_intervals_s", resyncIntervalsS)
            put("reconnect_count", reconnectCount)
            put("dropped_partial_count", droppedPartialCount)
        }
    }

    class CalibrationBuilder {
        private var leftQuatRef: FloatArray = floatArrayOf(1f, 0f, 0f, 0f)
        private var leftCalibratedAt: String = ""
        private var rightQuatRef: FloatArray = floatArrayOf(1f, 0f, 0f, 0f)
        private var rightCalibratedAt: String = ""

        fun left(quatRef: FloatArray, calibratedAt: String) = apply {
            this.leftQuatRef = quatRef
            this.leftCalibratedAt = calibratedAt
        }

        fun right(quatRef: FloatArray, calibratedAt: String) = apply {
            this.rightQuatRef = quatRef
            this.rightCalibratedAt = calibratedAt
        }

        fun build() = JSONObject().apply {
            put("left", JSONObject().apply {
                put("quat_ref", JSONArray(leftQuatRef.map { it.toDouble() }))
                put("calibrated_at", leftCalibratedAt)
            })
            put("right", JSONObject().apply {
                put("quat_ref", JSONArray(rightQuatRef.map { it.toDouble() }))
                put("calibrated_at", rightCalibratedAt)
            })
        }
    }
}
