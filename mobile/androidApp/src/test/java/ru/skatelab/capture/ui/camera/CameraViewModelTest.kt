package ru.skatelab.capture.ui.camera

import android.content.Context
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.viewModelScope
import io.mockk.Runs
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.just
import io.mockk.mockk
import io.mockk.mockkObject
import io.mockk.unmockkObject
import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.domain.service.ImuCollector
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.usecase.ReadSensorInfoUseCase
import ru.skatelab.capture.domain.usecase.RecordingStartInfo
import ru.skatelab.capture.domain.usecase.StartRecordingUseCase
import ru.skatelab.capture.domain.usecase.StopRecordingUseCase
import ru.skatelab.capture.upload.UploadScheduler

@OptIn(ExperimentalCoroutinesApi::class)
class CameraViewModelTest {
    private val dispatcher = UnconfinedTestDispatcher()
    private val testScope = TestScope(dispatcher)

    private lateinit var cameraRepository: CameraRepository
    private lateinit var bleRepository: BleRepository
    private lateinit var startRecordingUseCase: StartRecordingUseCase
    private lateinit var stopRecordingUseCase: StopRecordingUseCase
    private lateinit var readSensorInfoUseCase: ReadSensorInfoUseCase
    private lateinit var imuCollector: ImuCollector
    private lateinit var pendingUploadDao: PendingUploadDao
    private lateinit var appLogger: Logger
    private lateinit var appContext: Context
    private lateinit var lifecycleOwner: LifecycleOwner
    private lateinit var viewModel: CameraViewModel
    private lateinit var outputRoot: File

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
        outputRoot = Files.createTempDirectory("camera-view-model").toFile()

        cameraRepository = mockk(relaxed = true)
        bleRepository = mockk(relaxed = true)
        startRecordingUseCase = mockk()
        stopRecordingUseCase = mockk()
        readSensorInfoUseCase = mockk(relaxed = true)
        imuCollector = mockk(relaxed = true)
        pendingUploadDao = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)
        appContext = mockk(relaxed = true)
        lifecycleOwner = mockk(relaxed = true)

        every { appContext.getExternalFilesDir(any()) } returns outputRoot
        every { cameraRepository.surfaceRequest } returns MutableStateFlow(null)
        every { bleRepository.reconnectEvents } returns emptyFlow()
        coEvery { cameraRepository.bindToLifecycle(any()) } returns Result.success(Unit)
        mockkObject(UploadScheduler)
        every { UploadScheduler.enqueue(appContext, any()) } just Runs

        viewModel =
            CameraViewModel(
                cameraRepository = cameraRepository,
                bleRepository = bleRepository,
                startRecordingUseCase = startRecordingUseCase,
                stopRecordingUseCase = stopRecordingUseCase,
                readSensorInfoUseCase = readSensorInfoUseCase,
                imuCollector = imuCollector,
                pendingUploadDao = pendingUploadDao,
                appLogger = appLogger,
                appContext = appContext,
            )
    }

    @After
    fun tearDown() {
        viewModel.viewModelScope.cancel()
        testScope.cancel()
        Dispatchers.resetMain()
        outputRoot.deleteRecursively()
        unmockkObject(UploadScheduler)
    }

    private fun startInfo() =
        RecordingStartInfo(
            t0Ns = 10_000_000_000L,
            timestampSource = "BOOTTIME",
            videoStartDelayMs = 20L,
            imuStartDelayMs = mapOf(SensorId.LEFT to 5L, SensorId.RIGHT to 5L),
            videoFile = File(outputRoot, "video.mp4"),
            imuLeftFile = File(outputRoot, "left.binpb"),
            imuRightFile = File(outputRoot, "right.binpb"),
            framesFile = File(outputRoot, "frames.csv"),
        )

    private suspend fun TestScope.prepareCamera() {
        viewModel.bindCamera(lifecycleOwner)
        advanceUntilIdle()
        assertTrue(viewModel.isPreviewReady.value)
    }

    private suspend fun TestScope.startRecording() {
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns Result.success(startInfo())
        viewModel.startRecording(mockk())
        runCurrent()
        assertTrue(viewModel.isRecording.value)
    }

    @Test
    fun startRecording_startsCollectorBeforeUseCase_withBothSensorFiles() =
        testScope.runTest {
            prepareCamera()
            val lifecycle = mutableListOf<String>()
            every { imuCollector.start(any(), any()) } answers { lifecycle += "collector" }
            coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } coAnswers {
                lifecycle += "recording"
                Result.failure(IllegalStateException("camera test stop"))
            }

            viewModel.startRecording(mockk())
            advanceUntilIdle()

            assertEquals(listOf("collector", "recording"), lifecycle)
            io.mockk.verify {
                imuCollector.start(
                    any(),
                    match<Map<SensorId, File>> { files -> files.keys == setOf(SensorId.LEFT, SensorId.RIGHT) },
                )
            }
            assertFalse(viewModel.isRecording.value)
        }

    @Test
    fun startRecording_failure_stopsCollectorAndLeavesRecordingIdle() =
        testScope.runTest {
            prepareCamera()
            every { imuCollector.start(any(), any()) } answers { Unit }
            every { imuCollector.stop() } answers { emptyMap<SensorId, Int>() }
            coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
                Result.failure(IllegalStateException("BLE replay failed"))

            viewModel.startRecording(mockk())
            advanceUntilIdle()

            assertFalse(viewModel.isRecording.value)
            assertTrue(viewModel.error.value!!.contains("Recording start failed"))
            io.mockk.verify(exactly = 1) { imuCollector.stop() }
        }

    @Test
    fun stopRecording_writesManifestBeforeEnqueue_withBothImuPaths() =
        testScope.runTest {
            prepareCamera()
            startRecording()
            val lifecycle = mutableListOf<String>()
            every { imuCollector.firstSampleTimestampNs(SensorId.LEFT) } answers {
                lifecycle += "left-timestamp"
                10_100_000_000L
            }
            every { imuCollector.firstSampleTimestampNs(SensorId.RIGHT) } answers {
                lifecycle += "right-timestamp"
                10_110_000_000L
            }
            every { imuCollector.stop() } answers {
                lifecycle += "collector-stop"
                mapOf(SensorId.LEFT to 4, SensorId.RIGHT to 4)
            }
            coEvery { stopRecordingUseCase() } returns
                Result.success(
                    StopRecordingUseCase.StopResult(
                        actualFps = 60,
                        fpsVerified = true,
                        firstFrameNs = 10_000_000_000L,
                    ),
                )
            val inserted = mutableListOf<PendingUploadEntity>()
            coEvery { pendingUploadDao.insert(any()) } coAnswers {
                lifecycle += "insert"
                inserted += (args[0] as PendingUploadEntity)
            }
            every { UploadScheduler.enqueue(appContext, any()) } answers {
                lifecycle += "enqueue"
            }

            viewModel.stopRecording(mockk())
            advanceUntilIdle()

            val entity = inserted.single()
            val manifestPath = entity.manifestPath
            assertNotNull(manifestPath)
            val manifest = JSONObject(File(requireNotNull(manifestPath)).readText())
            assertEquals(10_000_000_000L, manifest.getLong("t0_ns"))
            assertEquals(10_100_000_000L, manifest.getJSONObject("imu").getJSONObject("left").getLong("first_timestamp_ns"))
            assertEquals(10_110_000_000L, manifest.getJSONObject("imu").getJSONObject("right").getLong("first_timestamp_ns"))
            assertEquals(startInfo().videoFile.absolutePath, entity.videoPath)
            assertEquals(startInfo().imuLeftFile.absolutePath, entity.imuLeftPath)
            assertEquals(startInfo().imuRightFile.absolutePath, entity.imuRightPath)
            assertTrue(manifestPath.endsWith("manifest.json"))
            assertTrue(lifecycle.indexOf("collector-stop") < lifecycle.indexOf("insert"))
            assertTrue(lifecycle.indexOf("insert") < lifecycle.indexOf("enqueue"))
            assertFalse(viewModel.isRecording.value)
        }

    @Test
    fun stopRecording_withoutActiveCapture_doesNotStopUseCaseOrCollector() =
        testScope.runTest {
            viewModel.stopRecording(mockk())
            advanceUntilIdle()

            assertEquals("No recording info", viewModel.error.value)
            coVerify(exactly = 0) { stopRecordingUseCase() }
            io.mockk.verify(exactly = 0) { imuCollector.stop() }
        }
}
