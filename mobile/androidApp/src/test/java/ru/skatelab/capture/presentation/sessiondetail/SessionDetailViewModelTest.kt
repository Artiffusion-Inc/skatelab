package ru.skatelab.capture.presentation.sessiondetail

import io.mockk.coEvery
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.SessionRepository

@OptIn(ExperimentalCoroutinesApi::class)
class SessionDetailViewModelTest {
    private val testDispatcher = UnconfinedTestDispatcher()

    private lateinit var sessionRepository: SessionRepository
    private lateinit var appLogger: AppLogger
    private lateinit var viewModel: SessionDetailViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        sessionRepository = mockk(relaxed = true)
        appLogger = mockk(relaxed = true)
        viewModel = SessionDetailViewModel(sessionRepository, appLogger)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun testSession(id: String = "sess-1") =
        CaptureSession(
            id = id,
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
            timestampSource = "REALTIME",
            videoStartDelayMs = 120L,
            imuStartDelayMs = mapOf(SensorId.LEFT to 480L, SensorId.RIGHT to 490L),
            calibration =
                mapOf(
                    SensorId.LEFT to CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L),
                    SensorId.RIGHT to CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L),
                ),
            clockOffsetNs = mapOf(SensorId.LEFT to 12345L, SensorId.RIGHT to 67890L),
            createdAt = 1_700_000_000_000L,
            isComplete = true,
        )

    @Test
    fun loadSession_updatesSessionFlow() =
        runTest {
            val session = testSession()
            coEvery { sessionRepository.getSession("sess-1") } returns session

            viewModel.loadSession("sess-1")
            advanceUntilIdle()

            assertEquals("sess-1", viewModel.session.value?.id)
            assertEquals(30, viewModel.session.value?.actualFps)
        }

    @Test
    fun loadSession_nullResult_setsNull() =
        runTest {
            coEvery { sessionRepository.getSession("missing") } returns null

            viewModel.loadSession("missing")
            advanceUntilIdle()

            assertNull(viewModel.session.value)
        }

    @Test
    fun updatePlaybackPosition_updatesFlow() {
        viewModel.updatePlaybackPosition(5000L)
        assertEquals(5000L, viewModel.playbackPositionMs.value)

        viewModel.updatePlaybackPosition(10000L)
        assertEquals(10000L, viewModel.playbackPositionMs.value)
    }

    @Test
    fun initialPlayPositionIsZero() {
        assertEquals(0L, viewModel.playbackPositionMs.value)
    }

    @Test
    fun initialImuDataIsNull() {
        assertNull(viewModel.imuData.value)
        assertFalse(viewModel.isImuLoading.value)
    }
}
