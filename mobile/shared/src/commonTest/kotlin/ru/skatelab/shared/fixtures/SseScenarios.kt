package ru.skatelab.shared.fixtures

import ru.skatelab.shared.models.ProcessEvent
import ru.skatelab.shared.models.ProcessStatus

/**
 * Pre-recorded SSE event sequences for testing.
 * Use with FakeProcessApi to simulate different processing scenarios.
 */
object SseScenarios {

    /** Happy path: queue → process → compute metrics → finish */
    val happyPath = listOf(
        ProcessEvent(progress = 0.05f, message = "Queuing...", status = "running"),
        ProcessEvent(progress = 0.2f, message = "Processing video...", status = "running"),
        ProcessEvent(progress = 0.5f, message = "Processing video...", status = "running"),
        ProcessEvent(progress = 0.7f, message = "Computing metrics...", status = "running"),
        ProcessEvent(progress = 0.9f, message = "Finishing up...", status = "running"),
        ProcessEvent(progress = 1.0f, message = "Done", status = "completed", sessionId = "sess-happy"),
    )

    /** Fast completion for quick E2E tests (<1s processing) */
    val fastCompletion = listOf(
        ProcessEvent(progress = 0.1f, message = "Queuing...", status = "running"),
        ProcessEvent(progress = 1.0f, message = "Done", status = "completed", sessionId = "sess-fast"),
    )

    /** Network error: server fails mid-processing */
    val networkError = listOf(
        ProcessEvent(progress = 0.3f, message = "Processing...", status = "running"),
        ProcessEvent(progress = 0.3f, message = "Connection lost", status = "failed"),
    )

    /** Server error: GPU processing fails */
    val serverError = listOf(
        ProcessEvent(progress = 0.1f, message = "Queuing...", status = "running"),
        ProcessEvent(progress = 0.1f, message = "GPU processing failed", status = "failed"),
    )

    /** Slow progress: many intermediate events (stress test) */
    val slowProgress = (0..20).map { i ->
        ProcessEvent(
            progress = i / 20f,
            message = "Step ${i + 1}/20",
            status = "running",
        )
    } + ProcessEvent(progress = 1.0f, message = "Done", status = "completed", sessionId = "sess-slow")
}