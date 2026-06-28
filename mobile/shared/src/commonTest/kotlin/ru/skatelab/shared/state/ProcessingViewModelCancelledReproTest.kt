package ru.skatelab.shared.state

import app.cash.turbine.test
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.api.QueueProcessResponse
import ru.skatelab.shared.api.TaskStatusResponse
import ru.skatelab.shared.models.ProcessEvent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * RED-by-design repro: ProcessingViewModel.observeProgress ignores ProcessStatus.CANCELLED.
 *
 * Bug: `when (event.parsedStatus) { ... else -> {} }` at ProcessingViewModel.kt:43
 * silently swallows a CANCELLED SSE event, so the UI stays stuck in Progress.
 *
 * This test feeds [RUNNING, CANCELLED] events via a FakeProcessApi, lets
 * startProcessing run to completion (the flow terminates after both events are
 * consumed), then asserts the final UI state is NOT Progress — it should be a
 * terminal state (Idle/Completed/Failed). Today the ViewModel ignores CANCELLED,
 * state stays Progress(0.5f, "Processing..."), and this test FAILS (RED) on the
 * assertFalse(state is Progress) assertion.
 *
 * No production code is touched by this commit. The fix belongs to a separate PR.
 *
 * See: GitHub issue "Mobile ProcessingViewModel.observeProgress ignores
 * ProcessStatus.CANCELLED -> UI stuck in Progress after cancel".
 */
class ProcessingViewModelCancelledReproTest {

    private class FakeProcessApi(
        private val streamEvents: List<ProcessEvent> = emptyList(),
    ) : IProcessApi {
        override suspend fun queue(
            videoKey: String,
            sessionId: String?,
            personClickX: Float?,
            personClickY: Float?,
            frameSkip: Int,
            tracking: String,
        ): QueueProcessResponse = QueueProcessResponse("task-1")

        override suspend fun status(taskId: String): TaskStatusResponse =
            TaskStatusResponse(taskId, "running", 0.5f, "Processing")

        override suspend fun cancel(taskId: String) {}

        override fun stream(taskId: String): Flow<ProcessEvent> =
            if (streamEvents.isEmpty()) flow { } else flowOf(*streamEvents.toTypedArray())
    }

    @Test
    fun startProcessing_onCancelledStatus_emitsTerminalStateNotProgress() = runTest {
        val fakeApi = FakeProcessApi(
            streamEvents = listOf(
                ProcessEvent(progress = 0.5f, message = "Processing...", status = "running"),
                ProcessEvent(progress = 0.5f, message = "Cancelled", status = "cancelled"),
            )
        )
        val viewModel = ProcessingViewModel(fakeApi)

        // Observe uiState emissions as startProcessing runs. The RUNNING event
        // transitions state to Progress (captured mid-stream as proof the RUNNING
        // branch fired); the CANCELLED event must then transition to a terminal
        // state (Idle/Completed/Failed), NOT stay in Progress.
        viewModel.uiState.test {
            assertEquals(ProcessingUiState.Idle, awaitItem())
            viewModel.startProcessing("video-key")

            // startProcessing sets Progress(0f, "Queuing...") before observeProgress.
            val queuing = awaitItem()
            assertIs<ProcessingUiState.Progress>(queuing)

            // The RUNNING SSE event -> Progress(0.5f, "Processing...").
            val running = awaitItem()
            assertIs<ProcessingUiState.Progress>(running)

            // The CANCELLED SSE event must transition out of Progress to a terminal
            // state (Idle — cancel returns to the pre-processing state). Today (RED)
            // the `when` block has `else -> {}` for CANCELLED, so no further emission
            // occurs and awaitItem() hangs until the Turbine scope is cancelled.
            val terminal = awaitItem()
            assertIs<ProcessingUiState.Idle>(terminal)
        }

        // After startProcessing returns (both events consumed), the UI must NOT be
        // stuck in Progress: a CANCELLED event is terminal.
        val finalState = viewModel.uiState.value
        assertFalse(
            actual = finalState is ProcessingUiState.Progress,
            message = "Expected terminal state after CANCELLED event, but UI is stuck in Progress: $finalState",
        )
    }
}