package ru.skatelab.shared.workflow

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class AnalysisWorkflowCoordinatorTest {
    @Test
    fun run_reachesCompletedThroughAllStates() = kotlinx.coroutines.test.runTest {
        val video = FakeVideoPort()
        val sessions = FakeSessionPort()
        val uploads = FakeUploadPort()
        val process = FakeProcessPort(
            updates = listOf(
                ProcessUpdate(ProcessUpdateStatus.RUNNING, progress = 0.5f, message = "Processing"),
                ProcessUpdate(ProcessUpdateStatus.COMPLETED, sessionId = "session-1"),
            ),
        )
        val coordinator = coordinator(video, sessions, uploads, process)
        coordinator.createDraft("analysis-1", AnalysisRequest())

        val result = coordinator.run("analysis-1")

        assertIs<AnalysisWorkflowState.Completed>(result.state)
        assertEquals("session-1", (result.state as AnalysisWorkflowState.Completed).sessionId)
        assertEquals(
            listOf("capture", "upload", "session", "queue"),
            videoAndNetworkCalls(video, sessions, uploads, process),
        )
    }

    @Test
    fun run_withoutTerminalUpdate_leavesProcessingForRecovery() = kotlinx.coroutines.test.runTest {
        val process = FakeProcessPort()
        val coordinator = coordinator(process = process)
        coordinator.createDraft("analysis-1", AnalysisRequest())

        val result = coordinator.run("analysis-1")

        assertIs<AnalysisWorkflowState.Processing>(result.state)
        assertEquals(1, process.queueCalls)
    }

    @Test
    fun queue_isIdempotentAfterTaskOwnershipIsSaved() = kotlinx.coroutines.test.runTest {
        val process = FakeProcessPort()
        val coordinator = coordinator(process = process)
        coordinator.createDraft("analysis-1", AnalysisRequest())
        coordinator.capture("analysis-1")
        coordinator.upload("analysis-1")

        val first = coordinator.queue("analysis-1")
        val second = coordinator.queue("analysis-1")

        assertEquals(first, second)
        assertEquals(1, process.queueCalls)
        assertEquals("analysis:analysis-1", process.requests.single().idempotencyKey)
    }

    @Test
    fun retry_afterQueueFailure_reusesSameQueueOwnership() = kotlinx.coroutines.test.runTest {
        val process = FakeProcessPort(queueFailures = 1)
        val coordinator = coordinator(process = process)
        coordinator.createDraft("analysis-1", AnalysisRequest())
        coordinator.capture("analysis-1")
        coordinator.upload("analysis-1")

        val failed = coordinator.queue("analysis-1")
        assertIs<AnalysisWorkflowState.Failed>(failed.state)
        val completedQueue = coordinator.retry("analysis-1")

        assertIs<AnalysisWorkflowState.Queued>(completedQueue.state)
        assertEquals(2, process.queueCalls)
        assertEquals(process.requests[0], process.requests[1])
    }

    @Test
    fun recover_processing_observesPersistedTaskWithoutQueuingAgain() = kotlinx.coroutines.test.runTest {
        val store = FakeWorkflowStore()
        store.save(
            AnalysisWorkflow(
                id = "analysis-1",
                state = AnalysisWorkflowState.Processing(
                    taskId = "task-1",
                    sessionId = "session-1",
                ),
            ),
        )
        val process = FakeProcessPort(
            updates = listOf(ProcessUpdate(ProcessUpdateStatus.COMPLETED)),
        )
        val coordinator = coordinator(store = store, process = process)

        val recovered = coordinator.recover("analysis-1")

        assertIs<AnalysisWorkflowState.Completed>(recovered.state)
        assertEquals("session-1", (recovered.state as AnalysisWorkflowState.Completed).sessionId)
        assertEquals(0, process.queueCalls)
        assertEquals(listOf("task-1"), process.observedTaskIds)
    }

    private fun coordinator(
        video: FakeVideoPort = FakeVideoPort(),
        sessions: FakeSessionPort = FakeSessionPort(),
        uploads: FakeUploadPort = FakeUploadPort(),
        process: FakeProcessPort = FakeProcessPort(),
        store: FakeWorkflowStore = FakeWorkflowStore(),
    ) = AnalysisWorkflowCoordinator(video, sessions, uploads, process, store)

    private fun videoAndNetworkCalls(
        video: FakeVideoPort,
        sessions: FakeSessionPort,
        uploads: FakeUploadPort,
        process: FakeProcessPort,
    ): List<String> = buildList {
        addAll(video.calls)
        addAll(uploads.calls)
        addAll(sessions.calls)
        addAll(process.calls)
    }

    private class FakeWorkflowStore : AnalysisWorkflowStore {
        private val workflows = linkedMapOf<String, AnalysisWorkflow>()

        override suspend fun get(workflowId: String): AnalysisWorkflow? = workflows[workflowId]

        override suspend fun save(workflow: AnalysisWorkflow) {
            workflows[workflow.id] = workflow
        }

        override suspend fun pending(): List<AnalysisWorkflow> = workflows.values.filter {
            it.state !is AnalysisWorkflowState.Completed &&
                it.state !is AnalysisWorkflowState.Failed &&
                it.state !is AnalysisWorkflowState.Cancelled
        }
    }

    private class FakeVideoPort : VideoPort {
        val calls = mutableListOf<String>()

        override suspend fun capture(workflowId: String, request: AnalysisRequest): CapturedVideo {
            calls += "capture"
            return CapturedVideo("capture-$workflowId")
        }
    }

    private class FakeSessionPort : SessionPort {
        val calls = mutableListOf<String>()

        override suspend fun create(workflowId: String, request: SessionRequest): Session {
            calls += "session"
            return Session("session-1")
        }
    }

    private class FakeUploadPort : UploadPort {
        val calls = mutableListOf<String>()

        override suspend fun upload(workflowId: String, video: CapturedVideo): UploadedVideo {
            calls += "upload"
            return UploadedVideo("video-$workflowId")
        }
    }

    private class FakeProcessPort(
        private val updates: List<ProcessUpdate> = emptyList(),
        private var queueFailures: Int = 0,
    ) : ProcessPort {
        val calls = mutableListOf<String>()
        val requests = mutableListOf<ProcessRequest>()
        val observedTaskIds = mutableListOf<String>()
        var queueCalls = 0
            private set

        override suspend fun queue(request: ProcessRequest): ProcessTask {
            calls += "queue"
            requests += request
            queueCalls++
            if (queueFailures > 0) {
                queueFailures--
                error("queue unavailable")
            }
            return ProcessTask("task-1")
        }

        override fun observe(taskId: String): Flow<ProcessUpdate> {
            observedTaskIds += taskId
            return flowOf(*updates.toTypedArray())
        }

        override suspend fun cancel(taskId: String) = Unit
    }
}
