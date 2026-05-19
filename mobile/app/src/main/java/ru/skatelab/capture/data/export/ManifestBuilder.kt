package ru.skatelab.capture.data.export

import javax.inject.Inject
import org.json.JSONArray
import org.json.JSONObject
import ru.skatelab.capture.domain.service.ManifestWriter

/**
 * Fluent builder for JSON manifest v2.0.
 * Produces the manifest.json file included in the capture ZIP export.
 */
class ManifestBuilder
    @Inject
    constructor() : ManifestWriter {
        private var version: String = "2.0"
        private var t0Ns: Long = 0L
        private var durationMs: Long = 0L
        private var video: JSONObject? = null
        private var imuLeft: JSONObject? = null
        private var imuRight: JSONObject? = null
        private var calibration: JSONObject? = null
        private var createdAt: String = ""

        override fun version(v: String): ManifestWriter = apply { this.version = v }

        override fun t0Ns(ns: Long): ManifestWriter = apply { this.t0Ns = ns }

        override fun durationMs(ms: Long): ManifestWriter = apply { this.durationMs = ms }

        override fun video(block: ManifestWriter.VideoBlock.() -> Unit): ManifestWriter =
            apply {
                video = VideoBuilder().apply(block).build()
            }

        override fun imu(
            side: String,
            block: ManifestWriter.ImuBlock.() -> Unit,
        ): ManifestWriter =
            apply {
                val entry = ImuEntryBuilder().apply(block).build()
                when (side.lowercase()) {
                    "left" -> imuLeft = entry
                    "right" -> imuRight = entry
                }
            }

        override fun calibration(block: ManifestWriter.CalibrationBlock.() -> Unit): ManifestWriter =
            apply {
                calibration = CalibrationBuilder().apply(block).build()
            }

        override fun createdAt(iso: String): ManifestWriter = apply { this.createdAt = iso }

        /** Build the manifest as a JSON string. */
        override fun build(): String {
            val root =
                JSONObject().apply {
                    put("version", version)
                    put("created_at", createdAt)
                    put("t0_ns", t0Ns)
                    put("duration_ms", durationMs)
                    video?.let { put("video", it) }
                    val imuObj =
                        JSONObject().apply {
                            imuLeft?.let { put("left", it) }
                            imuRight?.let { put("right", it) }
                        }
                    put("imu", imuObj)
                    calibration?.let { put("calibration", it) }
                }
            return root.toString(2)
        }

        class VideoBuilder : ManifestWriter.VideoBlock {
            private var filename: String = ""
            private var fps: Int = 60
            private var width: Int = 0
            private var height: Int = 0
            private var actualFpsVerified: Boolean = false
            private var frameTimestampsFile: String = ""
            private var timestampSource: String = "UNKNOWN"
            private var videoStartDelayMs: Long = 0L
            private var firstFrameNs: Long = 0L

            override fun filename(f: String) {
                this.filename = f
            }

            override fun fps(f: Int) {
                this.fps = f
            }

            override fun width(w: Int) {
                this.width = w
            }

            override fun height(h: Int) {
                this.height = h
            }

            override fun actualFpsVerified(v: Boolean) {
                this.actualFpsVerified = v
            }

            override fun frameTimestampsFile(f: String) {
                this.frameTimestampsFile = f
            }

            override fun timestampSource(s: String) {
                this.timestampSource = s
            }

            override fun videoStartDelayMs(ms: Long) {
                this.videoStartDelayMs = ms
            }

            override fun firstFrameNs(ns: Long) {
                this.firstFrameNs = ns
            }

            fun build() =
                JSONObject().apply {
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

        class ImuEntryBuilder : ManifestWriter.ImuBlock {
            private var filename: String = ""
            private var format: String = "delimited_imu_record"
            private var sampleRateHz: Int = 100
            private var sensorId: String = ""
            private var clockOffsetNs: Long = 0L
            private var imuStartDelayMs: Long = 0L
            private var resyncIntervalsS: Int = 30
            private var reconnectCount: Int = 0
            private var droppedPartialCount: Int = 0

            override fun filename(f: String) {
                this.filename = f
            }

            override fun format(f: String) {
                this.format = f
            }

            override fun sampleRateHz(hz: Int) {
                this.sampleRateHz = hz
            }

            override fun sensorId(id: String) {
                this.sensorId = id
            }

            override fun clockOffsetNs(ns: Long) {
                this.clockOffsetNs = ns
            }

            override fun imuStartDelayMs(ms: Long) {
                this.imuStartDelayMs = ms
            }

            override fun resyncIntervalsS(s: Int) {
                this.resyncIntervalsS = s
            }

            override fun reconnectCount(c: Int) {
                this.reconnectCount = c
            }

            override fun droppedPartialCount(c: Int) {
                this.droppedPartialCount = c
            }

            fun build() =
                JSONObject().apply {
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

        class CalibrationBuilder : ManifestWriter.CalibrationBlock {
            private var leftQuatRef: FloatArray = floatArrayOf(1f, 0f, 0f, 0f)
            private var leftCalibratedAt: String = ""
            private var rightQuatRef: FloatArray = floatArrayOf(1f, 0f, 0f, 0f)
            private var rightCalibratedAt: String = ""

            override fun left(
                quatRef: FloatArray,
                calibratedAt: String,
            ) {
                this.leftQuatRef = quatRef
                this.leftCalibratedAt = calibratedAt
            }

            override fun right(
                quatRef: FloatArray,
                calibratedAt: String,
            ) {
                this.rightQuatRef = quatRef
                this.rightCalibratedAt = calibratedAt
            }

            fun build() =
                JSONObject().apply {
                    put(
                        "left",
                        JSONObject().apply {
                            put("quat_ref", JSONArray(leftQuatRef.map { it.toDouble() }))
                            put("calibrated_at", leftCalibratedAt)
                        },
                    )
                    put(
                        "right",
                        JSONObject().apply {
                            put("quat_ref", JSONArray(rightQuatRef.map { it.toDouble() }))
                            put("calibrated_at", rightCalibratedAt)
                        },
                    )
                }
        }
    }
