package ru.skatelab.capture.presentation.export

import io.mockk.coEvery
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.data.share.ShareManager
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.usecase.ExportSessionUseCase

class ExportViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var exportUseCase: ExportSessionUseCase
    private lateinit var sessionRepository: SessionRepository
    private lateinit var shareManager: ShareManager
    private lateinit var viewModel: ExportViewModel

    private val stubSession =
        CaptureSession(
            id = "export-test",
            videoFile = File("/tmp/video.mp4"),
            imuLeftFile = File("/tmp/left.binpb"),
            imuRightFile = File("/tmp/right.binpb"),
            frameTimestampsFile = File("/tmp/frames.csv"),
            manifestFile = File("/tmp/manifest.json"),
            t0Ns = 1_000_000_000L,
            durationMs = 5000L,
            actualFps = 30,
            fpsVerified = true,
            firstFrameNs = 50_000_000L,
            timestampSource = "SENSOR",
            videoStartDelayMs = 120L,
            imuStartDelayMs = mapOf(SensorId.LEFT to 480L, SensorId.RIGHT to 490L),
            calibration = emptyMap(),
            clockOffsetNs = emptyMap(),
            createdAt = 1_700_000_000_000L,
            isComplete = true,
        )

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        exportUseCase = mockk()
        sessionRepository = mockk()
        shareManager = mockk(relaxed = true)
        viewModel = ExportViewModel(exportUseCase, sessionRepository, shareManager)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun export_success_setsExportPath() =
        testScope.runTest {
            val outputDir = createTempDir("export_test")
            val zipFile = File(outputDir, "${stubSession.id}.zip")

            coEvery { sessionRepository.getSession("export-test") } returns stubSession
            coEvery { exportUseCase.invoke(stubSession, any()) } returns Result.success(zipFile)

            viewModel.export("export-test", outputDir)
            runCurrent()

            assertTrue(viewModel.exportPath.value!!.endsWith(".zip"))
            assertNull(viewModel.error.value)
            outputDir.deleteRecursively()
        }

    @Test
    fun export_sessionNotFound_setsError() =
        testScope.runTest {
            val outputDir = createTempDir("export_test")
            coEvery { sessionRepository.getSession("missing") } returns null

            viewModel.export("missing", outputDir)
            runCurrent()

            assertTrue(viewModel.error.value!!.contains("Session not found"))
            outputDir.deleteRecursively()
        }

    @Test
    fun export_failure_setsError() =
        testScope.runTest {
            val outputDir = createTempDir("export_test")
            coEvery { sessionRepository.getSession("export-test") } returns stubSession
            coEvery { exportUseCase.invoke(stubSession, any()) } returns
                Result.failure(IllegalStateException("ZIP failed"))

            viewModel.export("export-test", outputDir)
            runCurrent()

            assertTrue(viewModel.error.value!!.contains("ZIP failed"))
            outputDir.deleteRecursively()
        }

    @Test
    fun export_resetsIsExporting() =
        testScope.runTest {
            val outputDir = createTempDir("export_test")
            coEvery { sessionRepository.getSession("export-test") } returns stubSession
            coEvery { exportUseCase.invoke(stubSession, any()) } returns
                Result.success(File(outputDir, "export-test.zip"))

            viewModel.export("export-test", outputDir)
            runCurrent()

            assertEquals(false, viewModel.isExporting.value)
            outputDir.deleteRecursively()
        }
}
