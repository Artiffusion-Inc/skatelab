package ru.skatelab.shared.state

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.api.QueueProcessResponse
import ru.skatelab.shared.api.TaskStatusResponse
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.ProcessEvent
import ru.skatelab.shared.models.ProcessStatus
import app.cash.turbine.test
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ProcessingViewModelTest {

    private class FakeProcessApi(
        private val queueResult: QueueProcessResponse = QueueProcessResponse("task-1"),
        private val queueException: Exception? = null,
        private val streamEvents: List<ProcessEvent> = emptyList(),
        private val cancelException: Exception? = null,
    ) : IProcessApi {
        override suspend fun queue(
            videoKey: String,
            sessionId: String?,
            personClickX: Float?,
            personClickY: Float?,
            frameSkip: Int,
            tracking: String,
        ): QueueProcessResponse {
            if (queueException != null) throw queueException
            return queueResult
        }

        override suspend fun status(taskId: String): TaskStatusResponse =
            TaskStatusResponse(taskId, "running", 0.5f, "Processing")

        override suspend fun cancel(taskId: String) {
            if (cancelException != null) throw cancelException
        }

        override fun stream(taskId: String): Flow<ProcessEvent> =
            if (streamEvents.isEmpty()) flow { } else flowOf(*streamEvents.toTypedArray())
    }

    @Test
    fun startProcessing_emitsProgressThenCompleted() = kotlinx.coroutines.test.runTest {
        val fakeApi = FakeProcessApi(
            streamEvents = listOf(
                ProcessEvent(progress = 0.5f, message = "Processing...", status = "running"),
                ProcessEvent(progress = 1.0f, message = "Done", status = "completed", sessionId = "sess-1"),
            )
        )
        val viewModel = ProcessingViewModel(fakeApi)

        viewModel.uiState.test {
            assertEquals(ProcessingUiState.Idle, awaitItem())
            viewModel.startProcessing("video-key")
            val queuing = awaitItem()
            assertIs<ProcessingUiState.Progress>(queuing)
            assertEquals("Queuing...", queuing.message)
            val running = awaitItem()
            assertIs<ProcessingUiState.Progress>(running)
            assertEquals(0.5f, running.percent)
            val completed = awaitItem()
            assertIs<ProcessingUiState.Completed>(completed)
            assertEquals("sess-1", completed.sessionId)
        }
    }

    @Test
    fun startProcessing_onQueueFailure_emitsFailed() = kotlinx.coroutines.test.runTest {
        val fakeApi = FakeProcessApi(
            queueException = RuntimeException("Server error")
        )
        val viewModel = ProcessingViewModel(fakeApi)

        viewModel.uiState.test {
            assertEquals(ProcessingUiState.Idle, awaitItem())
            viewModel.startProcessing("video-key")
            assertIs<ProcessingUiState.Progress>(awaitItem())
            val failed = awaitItem()
            assertIs<ProcessingUiState.Failed>(failed)
            assertIs<AppError.Unknown>(failed.error)
        }
    }

    @Test
    fun startProcessing_onStreamFailedStatus_emitsFailed() = kotlinx.coroutines.test.runTest {
        val fakeApi = FakeProcessApi(
            streamEvents = listOf(
                ProcessEvent(progress = 0.3f, message = "Processing...", status = "running"),
                ProcessEvent(progress = 0.5f, message = "GPU error", status = "failed"),
            )
        )
        val viewModel = ProcessingViewModel(fakeApi)

        viewModel.uiState.test {
            assertEquals(ProcessingUiState.Idle, awaitItem())
            viewModel.startProcessing("video-key")
            assertIs<ProcessingUiState.Progress>(awaitItem()) // Queuing...
            val running = awaitItem()
            assertIs<ProcessingUiState.Progress>(running)
            assertEquals(0.3f, running.percent)
            val failed = awaitItem()
            assertIs<ProcessingUiState.Failed>(failed)
            assertIs<AppError.Server>(failed.error)
        }
    }

    @Test
    fun cancelProcessing_succeeds() = kotlinx.coroutines.test.runTest {
        val fakeApi = FakeProcessApi(
            streamEvents = listOf(
                ProcessEvent(progress = 0.5f, message = "Processing...", status = "running"),
            ),
        )
        val viewModel = ProcessingViewModel(fakeApi)

        viewModel.startProcessing("video-key")
        advanceUntilIdle()
        // taskId is now stored in viewModel
        viewModel.cancelProcessing()
        advanceUntilIdle()
        // No exception = success
    }

    @Test
    fun cancelProcessing_onFailure_emitsFailed() = kotlinx.coroutines.test.runTest {
        val fakeApi = FakeProcessApi(
            streamEvents = listOf(
                ProcessEvent(progress = 0.5f, message = "Processing...", status = "running"),
            ),
            cancelException = RuntimeException("Cancel failed"),
        )
        val viewModel = ProcessingViewModel(fakeApi)

        viewModel.startProcessing("video-key")
        advanceUntilIdle()

        viewModel.uiState.test {
            viewModel.cancelProcessing()
            val failed = awaitItem()
            assertIs<ProcessingUiState.Failed>(failed)
            assertIs<AppError.Unknown>(failed.error)
        }
    }
}