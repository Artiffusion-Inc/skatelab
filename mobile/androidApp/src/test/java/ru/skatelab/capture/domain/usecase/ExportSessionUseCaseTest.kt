package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import ru.skatelab.capture.data.export.ManifestBuilder
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.service.SessionExporter

class ExportSessionUseCaseTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    private lateinit var sessionExporter: SessionExporter
    private lateinit var useCase: ExportSessionUseCase

    @Before
    fun setUp() {
        sessionExporter = mockk<SessionExporter>(relaxed = true)
        val manifestBuilder = ManifestBuilder()
        useCase = ExportSessionUseCase(sessionExporter, manifestBuilder)
    }

    private fun createTestSession(dir: File): CaptureSession {
        val videoFile = File(dir, "video.mp4").also { it.writeText("fake-video") }
        val imuLeft = File(dir, "imu_left.bin").also { it.writeText("fake-imu-left") }
        val imuRight = File(dir, "imu_right.bin").also { it.writeText("fake-imu-right") }
        val frameTimestamps = File(dir, "frame_ts.csv").also { it.writeText("0,1000,2000") }
        val manifest = File(dir, "manifest.json")

        return CaptureSession(
            id = "test-session",
            videoFile = videoFile,
            imuLeftFile = imuLeft,
            imuRightFile = imuRight,
            frameTimestampsFile = frameTimestamps,
            manifestFile = manifest,
            t0Ns = 1000000000L,
            durationMs = 5000L,
            actualFps = 30,
            fpsVerified = true,
            firstFrameNs = 1000000100L,
            videoWidth = 1920,
            videoHeight = 1080,
            timestampSource = "camera",
            videoStartDelayMs = 50L,
            imuStartDelayMs = mapOf(SensorId.LEFT to 10L, SensorId.RIGHT to 15L),
            calibration =
                mapOf(
                    SensorId.LEFT to CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L),
                ),
            clockOffsetNs = mapOf(SensorId.LEFT to 100L, SensorId.RIGHT to 200L),
            createdAt = System.currentTimeMillis(),
            isComplete = true,
        )
    }

    @Test
    fun invoke_exportsZipFile() =
        runTest {
            val sessionDir = tempFolder.newFolder("session")
            val session = createTestSession(sessionDir)
            val outputZip = File(tempFolder.root, "output.zip")

            val result = useCase.invoke(session, outputZip)

            assertTrue(result.isSuccess)
            coVerify { sessionExporter.export(any(), outputZip) }
        }

    @Test
    fun invoke_writesManifestFile() =
        runTest {
            val sessionDir = tempFolder.newFolder("session")
            val session = createTestSession(sessionDir)
            val outputZip = File(tempFolder.root, "output.zip")

            useCase.invoke(session, outputZip)

            val manifestFile = File(sessionDir, "manifest.json")
            assertTrue(manifestFile.exists())
            val content = manifestFile.readText()
            assertTrue(content.contains("\"version\""))
            assertTrue(content.contains("\"2.0\""))
            assertTrue(content.contains("\"t0_ns\""))
        }

    @Test
    fun invoke_propagatesExportError() =
        runTest {
            val sessionDir = tempFolder.newFolder("session")
            val session = createTestSession(sessionDir)
            val outputZip = File(tempFolder.root, "output.zip")

            coEvery { sessionExporter.export(any(), any()) } throws RuntimeException("Disk full")

            val result = useCase.invoke(session, outputZip)

            assertTrue(result.isFailure)
            assertEquals("Disk full", result.exceptionOrNull()!!.message)
        }
}
