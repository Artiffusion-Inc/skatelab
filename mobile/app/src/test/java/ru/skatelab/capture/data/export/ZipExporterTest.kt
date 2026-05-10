package ru.skatelab.capture.data.export

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.After
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import java.io.File
import java.util.zip.ZipFile

class ZipExporterTest {

    private lateinit var tempDir: File
    private lateinit var exporter: ZipExporter

    @Before
    fun setUp() {
        tempDir = createTempDir("zip_export_test")
        exporter = ZipExporter()
    }

    @After
    fun tearDown() {
        tempDir.deleteRecursively()
    }

    private fun createSessionWithFiles(): CaptureSession {
        val sessionDir = File(tempDir, "session-1")
        sessionDir.mkdirs()

        val videoFile = File(sessionDir, "video.mp4").also { it.writeText("video-data") }
        val imuLeftFile = File(sessionDir, "imu_left.binpb").also { it.writeText("left-imu-data") }
        val imuRightFile = File(sessionDir, "imu_right.binpb").also { it.writeText("right-imu-data") }
        val framesFile = File(sessionDir, "frames.csv").also { it.writeText("ts,frame\n0,1\n") }
        val manifestFile = File(sessionDir, "manifest.json").also { it.writeText("{\"version\":\"2.0\"}") }

        return CaptureSession(
            id = "session-1",
            videoFile = videoFile,
            imuLeftFile = imuLeftFile,
            imuRightFile = imuRightFile,
            frameTimestampsFile = framesFile,
            manifestFile = manifestFile,
            t0Ns = 1_000_000_000L,
            durationMs = 5000L,
            videoFps = 60,
            timestampSource = "REALTIME",
            videoStartDelayMs = 120L,
            imuStartDelayMs = mapOf(SensorId.LEFT to 480L, SensorId.RIGHT to 490L),
            calibration = mapOf(
                SensorId.LEFT to CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L),
                SensorId.RIGHT to CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L),
            ),
            clockOffsetNs = mapOf(SensorId.LEFT to 12345L, SensorId.RIGHT to 67890L),
            createdAt = 1_700_000_000_000L,
            isComplete = true,
        )
    }

    @Test
    fun exportCreatesZipWithAllSessionFiles() {
        val session = createSessionWithFiles()
        val zipFile = File(tempDir, "export.zip")

        exporter.export(session, zipFile)

        assertTrue("ZIP file should exist", zipFile.exists())

        val zip = ZipFile(zipFile)
        val entryNames = zip.entries().toList().map { it.name }.toSet()
        zip.close()

        assertTrue("ZIP should contain video file", entryNames.contains("video.mp4"))
        assertTrue("ZIP should contain left IMU file", entryNames.contains("imu_left.binpb"))
        assertTrue("ZIP should contain right IMU file", entryNames.contains("imu_right.binpb"))
        assertTrue("ZIP should contain frames file", entryNames.contains("frames.csv"))
        assertTrue("ZIP should contain manifest file", entryNames.contains("manifest.json"))
        assertEquals("ZIP should contain exactly 5 entries", 5, entryNames.size)
    }

    @Test
    fun exportSkipsMissingFiles() {
        val session = createSessionWithFiles()
        // Delete the video file to simulate a missing file
        session.videoFile.delete()
        assertFalse("Video file should be deleted", session.videoFile.exists())

        val zipFile = File(tempDir, "export.zip")
        exporter.export(session, zipFile)

        assertTrue("ZIP file should still be created", zipFile.exists())

        val zip = ZipFile(zipFile)
        val entryNames = zip.entries().toList().map { it.name }.toSet()
        zip.close()

        assertFalse("ZIP should not contain missing video file", entryNames.contains("video.mp4"))
        assertEquals("ZIP should contain 4 entries (without video)", 4, entryNames.size)
    }
}