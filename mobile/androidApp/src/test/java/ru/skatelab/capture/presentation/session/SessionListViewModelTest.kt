package ru.skatelab.capture.presentation.session

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.SessionRepository

class SessionListViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var sessionRepository: SessionRepository
    private lateinit var viewModel: SessionListViewModel

    private val stubSession =
        CaptureSession(
            id = "test-1",
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
        sessionRepository = mockk(relaxed = true)
        coEvery { sessionRepository.getSessions() } returns emptyList()
        viewModel = SessionListViewModel(sessionRepository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun init_loadsSessions() =
        testScope.runTest {
            advanceUntilIdle()
            coVerify { sessionRepository.getSessions() }
        }

    @Test
    fun loadSessions_populatesState() =
        testScope.runTest {
            coEvery { sessionRepository.getSessions() } returns listOf(stubSession)

            viewModel.loadSessions()
            advanceUntilIdle()

            assertEquals(1, viewModel.sessions.value.size)
            assertEquals("test-1", viewModel.sessions.value[0].id)
        }

    @Test
    fun loadSessions_emptyList() =
        testScope.runTest {
            coEvery { sessionRepository.getSessions() } returns emptyList()

            viewModel.loadSessions()
            advanceUntilIdle()

            assertTrue(viewModel.sessions.value.isEmpty())
        }

    @Test
    fun deleteSession_callsRepositoryAndReloads() =
        testScope.runTest {
            coEvery { sessionRepository.getSessions() } returns listOf(stubSession)
            coEvery { sessionRepository.deleteSession("test-1") } returns Result.success(Unit)

            viewModel.deleteSession("test-1")
            advanceUntilIdle()

            coVerify { sessionRepository.deleteSession("test-1") }
            coVerify(exactly = 2) { sessionRepository.getSessions() } // init + reload
        }
}
