package ru.skatelab.capture.ui.processing

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.api.QueueProcessResponse
import ru.skatelab.shared.models.ProcessEvent
import ru.skatelab.shared.state.ProcessingUiState
import ru.skatelab.shared.state.ProcessingViewModel

@OptIn(ExperimentalCoroutinesApi::class)
class AndroidProcessingViewModelTest {
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)

    private lateinit var processApi: IProcessApi
    private lateinit var viewModel: ProcessingViewModel

    @Before
    fun setUp() {
        processApi = mockk(relaxed = true)
        viewModel = ProcessingViewModel(processApi)
    }

    @Test
    fun startProcessing_queueFailure_setsFailedState() =
        testScope.runTest {
            coEvery { processApi.queue("bad-key", null) } throws RuntimeException("Queue error")

            viewModel.startProcessing("bad-key")
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is ProcessingUiState.Failed)
            assertTrue((state as ProcessingUiState.Failed).message.contains("Queue error"))
        }

    @Test
    fun startProcessing_completed_setsCompletedState() =
        testScope.runTest {
            coEvery { processApi.queue("good-key", null) } returns
                QueueProcessResponse(
                    taskId = "task-1", status = "pending",
                )
            every { processApi.stream("task-1") } returns
                flowOf(
                    ProcessEvent(progress = 1.0f, message = "Done", status = "completed", sessionId = "s1"),
                )

            viewModel.startProcessing("good-key")
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is ProcessingUiState.Completed)
            assertEquals("s1", (state as ProcessingUiState.Completed).sessionId)
        }

    @Test
    fun startProcessing_running_updatesProgress() =
        testScope.runTest {
            coEvery { processApi.queue("video", null) } returns
                QueueProcessResponse(
                    taskId = "task-2", status = "pending",
                )
            every { processApi.stream("task-2") } returns
                flowOf(
                    ProcessEvent(progress = 0.5f, message = "Processing", status = "running"),
                )

            viewModel.startProcessing("video")
            advanceUntilIdle()

            val state = viewModel.uiState.value
            assertTrue(state is ProcessingUiState.Progress)
            assertEquals(0.5f, (state as ProcessingUiState.Progress).percent, 0.01f)
        }

    @Test
    fun cancelProcessing_callsCancel() =
        testScope.runTest {
            coEvery { processApi.cancel("task-1") } returns Unit

            viewModel.cancelProcessing("task-1")
            advanceUntilIdle()

            // No state change expected (Idle remains)
            assertTrue(viewModel.uiState.value is ProcessingUiState.Idle)
        }
}
