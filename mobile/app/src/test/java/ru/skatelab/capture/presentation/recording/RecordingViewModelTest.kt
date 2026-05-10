package ru.skatelab.capture.presentation.recording

import android.content.Context
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.After
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.recording.ImuCollector
import ru.skatelab.capture.data.sync.PeriodicTimeSync
import ru.skatelab.capture.data.sync.TimeSyncManager
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.usecase.RecordingStartInfo
import ru.skatelab.capture.domain.usecase.StartRecordingUseCase
import ru.skatelab.capture.domain.usecase.StopRecordingUseCase
import java.io.File

class RecordingViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var cameraRepository: CameraRepository
    private lateinit var bleRepository: BleRepository
    private lateinit var imuCollector: ImuCollector
    private lateinit var sessionRepository: SessionRepository
    private lateinit var startRecordingUseCase: StartRecordingUseCase
    private lateinit var stopRecordingUseCase: StopRecordingUseCase
    private lateinit var timeSyncManager: TimeSyncManager
    private lateinit var periodicTimeSync: PeriodicTimeSync
    private lateinit var appLogger: AppLogger
    private lateinit var context: Context
    private lateinit var viewModel: RecordingViewModel

    private val outputDir = File("/tmp/test-output")
    private val videoFile = File(outputDir, "video.mp4")
    private val framesFile = File(outputDir, "frames.csv")
    private val imuLeftFile = File(outputDir, "imu_left.binpb")
    private val imuRightFile = File(outputDir, "imu_right.binpb")

    private val stubStartInfo = RecordingStartInfo(
        t0Ns = 1_000_000_000L,
        timestampSource = "SENSOR",
        videoStartDelayMs = 50L,
        imuStartDelayMs = mapOf(SensorId.LEFT to 10L, SensorId.RIGHT to 10L),
        videoFile = videoFile,
        imuLeftFile = imuLeftFile,
        imuRightFile = imuRightFile,
        framesFile = framesFile,
    )

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)

        cameraRepository = mockk(relaxed = true)
        bleRepository = mockk(relaxed = true)
        imuCollector = mockk(relaxed = true)
        sessionRepository = mockk(relaxed = true)
        startRecordingUseCase = mockk()
        stopRecordingUseCase = mockk()
        timeSyncManager = mockk(relaxed = true)
        periodicTimeSync = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)
        context = mockk(relaxed = true)

        every { cameraRepository.isRecording } returns MutableStateFlow(false)
        every { cameraRepository.previewSurface } returns MutableStateFlow(null)
        every { timeSyncManager.getOffset(any()) } returns 0L
        every { bleRepository.reconnectEvents } returns kotlinx.coroutines.flow.emptyFlow()

        viewModel = RecordingViewModel(
            cameraRepository, bleRepository, imuCollector, sessionRepository,
            startRecordingUseCase, stopRecordingUseCase,
            timeSyncManager, periodicTimeSync, appLogger,
        )
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun prepareCamera_setsIsPreviewReady() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)

        viewModel.prepareCamera(outputDir)
        runCurrent()

        assertTrue(viewModel.isPreviewReady.value)
        assertNull(viewModel.error.value)
    }

    @Test
    fun prepareCameraFailure_setsError() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns
            Result.failure(IllegalStateException("Camera busy"))

        viewModel.prepareCamera(outputDir)
        runCurrent()

        assertFalse(viewModel.isPreviewReady.value)
        assertTrue(viewModel.error.value!!.contains("Camera prepare failed"))
    }

    @Test
    fun startRecording_setsIsRecording() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.success(stubStartInfo)

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        assertTrue(viewModel.isRecording.value)
        assertNull(viewModel.error.value)
        verify { imuCollector.start(any(), any()) }
        coVerify { periodicTimeSync.sync(any()) }
        coVerify { periodicTimeSync.awaitSync() }
    }

    @Test
    fun startRecordingFailure_doesNotSetRecording() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.failure(IllegalStateException("BLE start failed"))

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        assertFalse(viewModel.isRecording.value)
        assertTrue(viewModel.error.value!!.contains("Recording start failed"))
    }

    @Test
    fun startRecording_withoutPrepare_setsError() = testScope.runTest {
        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        assertFalse(viewModel.isRecording.value)
        assertTrue(viewModel.error.value!!.contains("Camera not prepared"))
    }

    @Test
    fun stopRecording_setsSessionId() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.success(stubStartInfo)
        coEvery { stopRecordingUseCase() } returns Result.success(Unit)
        coEvery { sessionRepository.saveSession(any()) } returns Result.success(Unit)
        every { imuCollector.stop() } returns emptyMap()

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        viewModel.stopRecording(context)
        runCurrent()

        assertTrue("sessionId should be set", viewModel.sessionId.value != null)
        assertFalse(viewModel.isRecording.value)
        assertFalse(viewModel.isPreviewReady.value)
        coVerify { sessionRepository.saveSession(any()) }
        verify { periodicTimeSync.stop() }
    }

    @Test
    fun stopRecording_withoutActiveStart_setsError() = testScope.runTest {
        viewModel.stopRecording(context)
        runCurrent()

        assertTrue(viewModel.error.value!!.contains("No active recording"))
    }

    @Test
    fun stopRecording_saveSessionFailure_stillSetsSessionId() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.success(stubStartInfo)
        coEvery { stopRecordingUseCase() } returns Result.success(Unit)
        coEvery { sessionRepository.saveSession(any()) } returns
            Result.failure(IllegalStateException("DB error"))
        every { imuCollector.stop() } returns emptyMap()

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        viewModel.stopRecording(context)
        runCurrent()

        assertTrue("sessionId should be set", viewModel.sessionId.value != null)
        assertFalse(viewModel.isRecording.value)
    }

    @Test
    fun stopRecording_preservesCalibration() = testScope.runTest {
        val calibration = mapOf(
            SensorId.LEFT to CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 100L),
            SensorId.RIGHT to CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 200L),
        )

        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.success(stubStartInfo)
        coEvery { stopRecordingUseCase() } returns Result.success(Unit)
        coEvery { sessionRepository.saveSession(any()) } returns Result.success(Unit)
        every { imuCollector.stop() } returns emptyMap()

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, calibration, context)
        runCurrent()

        viewModel.stopRecording(context)
        runCurrent()

        coVerify { sessionRepository.saveSession(match { it.calibration == calibration }) }
    }

    @Test
    fun imuCollectorStarted_onRecordingStart() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.success(stubStartInfo)

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        verify { imuCollector.start(any(), any()) }
    }

    @Test
    fun imuCollectorStopped_onRecordingStop() = testScope.runTest {
        coEvery { cameraRepository.prepare(any(), any()) } returns Result.success(Unit)
        coEvery { startRecordingUseCase(any(), any(), any(), any(), any()) } returns
            Result.success(stubStartInfo)
        coEvery { stopRecordingUseCase() } returns Result.success(Unit)
        coEvery { sessionRepository.saveSession(any()) } returns Result.success(Unit)
        every { imuCollector.stop() } returns mapOf(SensorId.LEFT to 100, SensorId.RIGHT to 95)

        viewModel.prepareCamera(outputDir)
        runCurrent()

        viewModel.startRecording(outputDir, emptyMap(), context)
        runCurrent()

        viewModel.stopRecording(context)
        runCurrent()

        verify { imuCollector.stop() }
    }
}
