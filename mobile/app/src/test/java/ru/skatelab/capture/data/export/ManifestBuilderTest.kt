package ru.skatelab.capture.data.export

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ManifestBuilderTest {
    @Test
    fun `build manifest and verify JSON fields`() {
        val json =
            ManifestBuilder()
                .version("2.0")
                .t0Ns(12345678901200L)
                .durationMs(5000L)
                .createdAt("2026-05-09T14:30:00Z")
                .video {
                    filename("capture_20260509_143000.mp4")
                    fps(60)
                    width(1920)
                    height(1080)
                    actualFpsVerified(true)
                    frameTimestampsFile("capture_20260509_143000_frames.csv")
                    timestampSource("REALTIME")
                    videoStartDelayMs(120L)
                    firstFrameNs(12345678901200L)
                }
                .imu("left") {
                    filename("capture_20260509_143000_left.binpb")
                    format("delimited_imu_record")
                    sampleRateHz(100)
                    sensorId("WT901-XXXX")
                    clockOffsetNs(12345L)
                    imuStartDelayMs(480L)
                    resyncIntervalsS(30)
                    reconnectCount(0)
                    droppedPartialCount(0)
                }
                .imu("right") {
                    filename("capture_20260509_143000_right.binpb")
                    format("delimited_imu_record")
                    sampleRateHz(100)
                    sensorId("WT901-YYYY")
                    clockOffsetNs(67890L)
                    imuStartDelayMs(490L)
                    resyncIntervalsS(30)
                    reconnectCount(1)
                    droppedPartialCount(2)
                }
                .calibration {
                    left(floatArrayOf(1f, 0f, 0f, 0f), "2026-05-09T14:29:50Z")
                    right(floatArrayOf(1f, 0f, 0f, 0f), "2026-05-09T14:29:50Z")
                }
                .build()

        val root = JSONObject(json)

        // Top-level fields
        assertEquals("2.0", root.getString("version"))
        assertEquals(12345678901200L, root.getLong("t0_ns"))
        assertEquals(5000L, root.getLong("duration_ms"))
        assertEquals("2026-05-09T14:30:00Z", root.getString("created_at"))

        // Video fields
        val video = root.getJSONObject("video")
        assertEquals("capture_20260509_143000.mp4", video.getString("filename"))
        assertEquals(60, video.getInt("fps"))
        assertEquals(1920, video.getInt("width"))
        assertEquals(1080, video.getInt("height"))
        assertTrue(video.getBoolean("actual_fps_verified"))
        assertEquals("REALTIME", video.getString("timestamp_source"))
        assertEquals(120L, video.getLong("video_start_delay_ms"))
        assertEquals(12345678901200L, video.getLong("first_frame_ns"))

        // IMU left fields
        val imu = root.getJSONObject("imu")
        val left = imu.getJSONObject("left")
        assertEquals("capture_20260509_143000_left.binpb", left.getString("filename"))
        assertEquals("delimited_imu_record", left.getString("format"))
        assertEquals(100, left.getInt("sample_rate_hz"))
        assertEquals("WT901-XXXX", left.getString("sensor_id"))
        assertEquals(12345L, left.getLong("clock_offset_ns"))
        assertEquals(480L, left.getLong("imu_start_delay_ms"))
        assertEquals(0, left.getInt("reconnect_count"))

        // IMU right fields
        val right = imu.getJSONObject("right")
        assertEquals("capture_20260509_143000_right.binpb", right.getString("filename"))
        assertEquals(67890L, right.getLong("clock_offset_ns"))
        assertEquals(1, right.getInt("reconnect_count"))
        assertEquals(2, right.getInt("dropped_partial_count"))

        // Calibration fields
        val calibration = root.getJSONObject("calibration")
        val leftCal = calibration.getJSONObject("left")
        val leftQuat = leftCal.getJSONArray("quat_ref")
        assertEquals(1.0, leftQuat.getDouble(0), 0.001)
        assertEquals(0.0, leftQuat.getDouble(1), 0.001)
        assertEquals("2026-05-09T14:29:50Z", leftCal.getString("calibrated_at"))
    }

    @Test
    fun `minimal manifest with only required fields`() {
        val json =
            ManifestBuilder()
                .t0Ns(1000L)
                .durationMs(100L)
                .createdAt("2026-01-01T00:00:00Z")
                .build()

        val root = JSONObject(json)
        assertEquals("2.0", root.getString("version"))
        assertEquals(1000L, root.getLong("t0_ns"))
        assertEquals(100L, root.getLong("duration_ms"))
    }
}
