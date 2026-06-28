package ru.skatelab.shared.state

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.api.QueueProcessResponse
import ru.skatelab.shared.api.TaskStatusResponse
import ru.skatelab.shared.models.ProcessEvent
import kotlin.test.Test
import kotlin.test.assertFalse
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
    fun startProcessing_onCancelledStatus_emitsTerminalStateNotProgress() = kotlinx.coroutines.test.runTest {
        val fakeApi = FakeProcessApi(
            streamEvents = listOf(
                ProcessEvent(progress = 0.5f, message = "Processing...", status = "running"),
                ProcessEvent(progress = 0.5f, message = "Cancelled", status = "cancelled"),
            )
        )
        val viewModel = ProcessingViewModel(fakeApi)

        // startProcessing suspends until the stream completes (both events
        // consumed). The RUNNING event transitions state to Progress; the
        // CANCELLED event is swallowed by `else -> {}`, so state stays Progress.
        viewModel.startProcessing("video-key")

        // Sanity: the RUNNING event was processed -> state reached Progress.
        assertTrue(
            actual = viewModel.uiState.value is ProcessingUiState.Progress,
            message = "Precondition: state should be Progress after RUNNING event, got ${viewModel.uiState.value}",
        )

        // BUG REPRO: after a CANCELLED event the UI must be in a terminal state
        // (Idle/Completed/Failed), NOT Progress. Today this is RED because the
        // ViewModel's `when` block has `else -> {}` for CANCELLED and never
        // transitions out of Progress.
        assertFalse(
            actual = viewModel.uiState.value is ProcessingUiState.Progress,
            message = "Expected terminal state after CANCELLED event, but UI is stuck in Progress: ${viewModel.uiState.value}",
        )
    }
}