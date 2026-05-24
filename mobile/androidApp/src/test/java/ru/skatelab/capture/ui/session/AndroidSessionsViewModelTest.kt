package ru.skatelab.capture.ui.session

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.models.SessionListResponse
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.state.SessionsUiState
import ru.skatelab.shared.state.SessionsViewModel

@OptIn(ExperimentalCoroutinesApi::class)
class AndroidSessionsViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var sessionsApi: SessionsApi
    private lateinit var viewModel: SessionsViewModel

    @Before
    fun setUp() {
        sessionsApi = mockk(relaxed = true)
        viewModel = SessionsViewModel(sessionsApi)
    }

    @Test
    fun loadSessions_success_setsLoadedState() =
        testScope.runTest {
            val sessions =
                listOf(
                    SessionResponse(
                        id = "s1", userId = "u1", elementType = "axel",
                        videoUrl = null, processedVideoUrl = null, status = "completed",
                        overallScore = 90f, recommendations = null, metrics = emptyList(),
                        createdAt = "2026-05-24T10:00:00Z",
                    ),
                )
            coEvery { sessionsApi.list(20, 0) } returns
                SessionListResponse(
                    sessions = sessions, total = 1, page = 1, pageSize = 20, pages = 1,
                )

            viewModel.loadSessions()
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is SessionsUiState.Loaded)
            assertEquals(1, (state as SessionsUiState.Loaded).sessions.size)
            assertEquals("s1", state.sessions[0].id)
        }

    @Test
    fun loadSessions_failure_setsErrorState() =
        testScope.runTest {
            coEvery { sessionsApi.list(any(), any()) } throws RuntimeException("Network error")

            viewModel.loadSessions()
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is SessionsUiState.Error)
            assertTrue((state as SessionsUiState.Error).message.contains("Network error"))
        }

    @Test
    fun loadSession_success_setsSelectedSession() =
        testScope.runTest {
            val session =
                SessionResponse(
                    id = "s1", userId = "u1", elementType = "lutz",
                    videoUrl = null, processedVideoUrl = null, status = "completed",
                    overallScore = 85f, recommendations = null, metrics = emptyList(),
                    createdAt = "2026-05-24T10:00:00Z",
                )
            coEvery { sessionsApi.get("s1") } returns session

            viewModel.loadSession("s1")
            advanceUntilIdle()

            val selected = viewModel.selectedSession.value
            assertEquals("s1", selected?.id)
            assertEquals("lutz", selected?.elementType)
        }

    @Test
    fun loadSession_failure_setsErrorState() =
        testScope.runTest {
            coEvery { sessionsApi.get("bad") } throws RuntimeException("Not found")

            viewModel.loadSession("bad")
            advanceUntilIdle()

            assertTrue(viewModel.uiState.value is SessionsUiState.Error)
        }
}
