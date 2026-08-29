package ru.skatelab.shared.workflow

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class AnalysisWorkflowCoordinator(
    private val videoPort: VideoPort,
    private val sessionPort: SessionPort,
    private val uploadPort: UploadPort,
    private val processPort: ProcessPort,
    private val store: AnalysisWorkflowStore,
) {
    private val mutationMutex = Mutex()

    suspend fun createDraft(workflowId: String, request: AnalysisRequest): AnalysisWorkflow {
        require(workflowId.isNotBlank()) { "workflowId must not be blank" }
        return mutationMutex.withLock {
            store.get(workflowId) ?: AnalysisWorkflow(workflowId, AnalysisWorkflowState.Draft(request)).also {
                store.save(it)
            }
        }
    }

    suspend fun capture(workflowId: String): AnalysisWorkflow = capture(workflowId, retryCount = 0)

    private suspend fun capture(workflowId: String, retryCount: Int): AnalysisWorkflow =
        mutationMutex.withLock {
            val current = requireWorkflow(workflowId)
            val request = when (val state = current.state) {
                is AnalysisWorkflowState.Draft -> state.request
                is AnalysisWorkflowState.Capture -> state.request
                else -> return@withLock current
            }
            store.save(current.copy(state = AnalysisWorkflowState.Capture(request)))
            try {
                val video = videoPort.capture(workflowId, request)
                AnalysisWorkflow(workflowId, AnalysisWorkflowState.Uploading(request, video)).also {
                    store.save(it)
                }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                failed(
                    current = AnalysisWorkflow(workflowId, AnalysisWorkflowState.Capture(request)),
                    work = RetryWork.Capture(request),
                    error = error,
                    retryCount = retryCount + 1,
                )
            }
        }

    suspend fun upload(workflowId: String): AnalysisWorkflow = upload(workflowId, retryCount = 0)

    private suspend fun upload(workflowId: String, retryCount: Int): AnalysisWorkflow =
        mutationMutex.withLock {
            val current = requireWorkflow(workflowId)
            val uploading = current.state as? AnalysisWorkflowState.Uploading
                ?: return@withLock current
            var uploaded = uploading.uploaded
            if (uploaded == null) {
                uploaded = try {
                    uploadPort.upload(workflowId, uploading.video)
                } catch (error: CancellationException) {
                    throw error
                } catch (error: Exception) {
                    return@withLock failed(
                        current = current,
                        work = RetryWork.Upload(uploading.request, uploading.video, null),
                        error = error,
                        retryCount = retryCount + 1,
                    )
                }
                store.save(current.copy(state = uploading.copy(uploaded = uploaded)))
            }
            try {
                val session = sessionPort.create(
                    workflowId,
                    SessionRequest(videoKey = uploaded.key, elementType = uploading.request.elementType),
                )
                val request = ProcessRequest(
                    workflowId = workflowId,
                    sessionId = session.id,
                    videoKey = uploaded.key,
                    idempotencyKey = queueOwnershipKey(workflowId),
                )
                AnalysisWorkflow(workflowId, AnalysisWorkflowState.Queued(request)).also { store.save(it) }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                failed(
                    current = store.get(workflowId) ?: current,
                    work = RetryWork.Upload(uploading.request, uploading.video, uploaded),
                    error = error,
                    retryCount = retryCount + 1,
                )
            }
        }

    suspend fun queue(workflowId: String): AnalysisWorkflow = queue(workflowId, retryCount = 0)

    private suspend fun queue(workflowId: String, retryCount: Int): AnalysisWorkflow =
        mutationMutex.withLock {
            val current = requireWorkflow(workflowId)
            val queued = current.state as? AnalysisWorkflowState.Queued
                ?: return@withLock current
            if (queued.taskId != null) return@withLock current
            try {
                val task = processPort.queue(queued.request)
                AnalysisWorkflow(workflowId, queued.copy(taskId = task.taskId)).also { store.save(it) }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                failed(
                    current = current,
                    work = RetryWork.Queue(queued.request),
                    error = error,
                    retryCount = retryCount + 1,
                )
            }
        }

    suspend fun process(workflowId: String): AnalysisWorkflow = process(workflowId, retryCount = 0)

    private suspend fun process(workflowId: String, retryCount: Int): AnalysisWorkflow {
        val target = mutationMutex.withLock {
            val current = requireWorkflow(workflowId)
            when (val state = current.state) {
                is AnalysisWorkflowState.Queued -> {
                    val taskId = state.taskId ?: return@withLock null
                    ProcessTarget(taskId, state.request.sessionId).also {
                        store.save(
                            AnalysisWorkflow(
                                workflowId,
                                AnalysisWorkflowState.Processing(taskId, state.request.sessionId),
                            ),
                        )
                    }
                }
                is AnalysisWorkflowState.Processing -> ProcessTarget(state.taskId, state.sessionId)
                else -> return@withLock null
            }
        } ?: return requireWorkflow(workflowId)

        try {
            processPort.observe(target.taskId).collect { update ->
                mutationMutex.withLock {
                    val current = store.get(workflowId) ?: return@withLock
                    if (current.state is AnalysisWorkflowState.Completed ||
                        current.state is AnalysisWorkflowState.Failed ||
                        current.state is AnalysisWorkflowState.Cancelled
                    ) {
                        return@withLock
                    }
                    when (update.status) {
                        ProcessUpdateStatus.RUNNING -> store.save(
                            AnalysisWorkflow(
                                workflowId,
                                AnalysisWorkflowState.Processing(
                                    taskId = target.taskId,
                                    sessionId = target.sessionId,
                                    progress = update.progress,
                                    message = update.message,
                                ),
                            ),
                        )
                        ProcessUpdateStatus.COMPLETED -> store.save(
                            AnalysisWorkflow(
                                workflowId,
                                AnalysisWorkflowState.Completed(update.sessionId ?: target.sessionId),
                            ),
                        )
                        ProcessUpdateStatus.FAILED -> failed(
                            current = current,
                            work = RetryWork.Process(target.taskId, target.sessionId),
                            message = update.error ?: update.message.ifBlank { "processing failed" },
                            retryCount = retryCount + 1,
                        )
                        ProcessUpdateStatus.CANCELLED -> store.save(
                            AnalysisWorkflow(
                                workflowId,
                                AnalysisWorkflowState.Cancelled(update.message.ifBlank { null }),
                            ),
                        )
                    }
                }
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            val current = store.get(workflowId) ?: return requireWorkflow(workflowId)
            if (current.state is AnalysisWorkflowState.Processing) {
                failed(
                    current = current,
                    work = RetryWork.Process(target.taskId, target.sessionId),
                    error = error,
                    retryCount = retryCount + 1,
                )
            }
        }
        return requireWorkflow(workflowId)
    }

    suspend fun cancel(workflowId: String): AnalysisWorkflow = mutationMutex.withLock {
        val current = requireWorkflow(workflowId)
        when (val state = current.state) {
            is AnalysisWorkflowState.Draft,
            is AnalysisWorkflowState.Capture,
            is AnalysisWorkflowState.Uploading,
            -> AnalysisWorkflow(workflowId, AnalysisWorkflowState.Cancelled()).also { store.save(it) }
            is AnalysisWorkflowState.Queued -> {
                val taskId = state.taskId
                if (taskId == null) {
                    AnalysisWorkflow(workflowId, AnalysisWorkflowState.Cancelled()).also { store.save(it) }
                } else {
                    try {
                        processPort.cancel(taskId)
                        AnalysisWorkflow(workflowId, AnalysisWorkflowState.Cancelled()).also { store.save(it) }
                    } catch (error: CancellationException) {
                        throw error
                    } catch (error: Exception) {
                        failed(current, RetryWork.Cancel(taskId), error, retryCount = 1)
                    }
                }
            }
            is AnalysisWorkflowState.Processing -> try {
                processPort.cancel(state.taskId)
                AnalysisWorkflow(workflowId, AnalysisWorkflowState.Cancelled()).also { store.save(it) }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                failed(current, RetryWork.Cancel(state.taskId), error, retryCount = 1)
            }
            is AnalysisWorkflowState.Completed,
            is AnalysisWorkflowState.Failed,
            is AnalysisWorkflowState.Cancelled,
            -> current
        }
    }

    suspend fun retry(workflowId: String): AnalysisWorkflow {
        val current = requireWorkflow(workflowId)
        val failed = current.state as? AnalysisWorkflowState.Failed ?: return current
        return when (val work = failed.work) {
            is RetryWork.Capture -> {
                store.save(current.copy(state = AnalysisWorkflowState.Capture(work.request)))
                capture(workflowId, failed.retryCount)
            }
            is RetryWork.Upload -> {
                store.save(
                    current.copy(
                        state = AnalysisWorkflowState.Uploading(work.request, work.video, work.uploaded),
                    ),
                )
                upload(workflowId, failed.retryCount)
            }
            is RetryWork.Queue -> {
                store.save(current.copy(state = AnalysisWorkflowState.Queued(work.request)))
                queue(workflowId, failed.retryCount)
            }
            is RetryWork.Process -> {
                store.save(
                    current.copy(
                        state = AnalysisWorkflowState.Processing(work.taskId, work.sessionId),
                    ),
                )
                process(workflowId, failed.retryCount)
            }
            is RetryWork.Cancel -> try {
                processPort.cancel(work.taskId)
                AnalysisWorkflow(workflowId, AnalysisWorkflowState.Cancelled()).also { store.save(it) }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                failed(current, work, error, failed.retryCount + 1)
            }
        }
    }

    suspend fun run(workflowId: String): AnalysisWorkflow {
        while (true) {
            val current = requireWorkflow(workflowId)
            val next = when (val state = current.state) {
                is AnalysisWorkflowState.Draft,
                is AnalysisWorkflowState.Capture,
                -> capture(workflowId)
                is AnalysisWorkflowState.Uploading -> upload(workflowId)
                is AnalysisWorkflowState.Queued -> if (state.taskId == null) queue(workflowId) else process(workflowId)
                is AnalysisWorkflowState.Processing -> process(workflowId)
                is AnalysisWorkflowState.Completed,
                is AnalysisWorkflowState.Failed,
                is AnalysisWorkflowState.Cancelled,
                -> return current
            }
            // An interrupted stream leaves a recoverable Processing state; do not spin.
            if (next.state is AnalysisWorkflowState.Processing ||
                next.state is AnalysisWorkflowState.Failed
            ) return next
        }
    }

    suspend fun recover(workflowId: String): AnalysisWorkflow {
        return when (val state = requireWorkflow(workflowId).state) {
            is AnalysisWorkflowState.Draft -> requireWorkflow(workflowId)
            is AnalysisWorkflowState.Capture -> capture(workflowId)
            is AnalysisWorkflowState.Uploading -> upload(workflowId)
            is AnalysisWorkflowState.Queued -> if (state.taskId == null) queue(workflowId) else process(workflowId)
            is AnalysisWorkflowState.Processing -> process(workflowId)
            is AnalysisWorkflowState.Completed,
            is AnalysisWorkflowState.Failed,
            is AnalysisWorkflowState.Cancelled,
            -> requireWorkflow(workflowId)
        }
    }

    suspend fun recover(): List<AnalysisWorkflow> = store.pending().map { recover(it.id) }

    private suspend fun requireWorkflow(workflowId: String): AnalysisWorkflow =
        store.get(workflowId) ?: error("Unknown workflow: $workflowId")

    private suspend fun failed(
        current: AnalysisWorkflow,
        work: RetryWork,
        error: Exception,
        retryCount: Int,
    ): AnalysisWorkflow = failed(current, work, error.message ?: "operation failed", retryCount)

    private suspend fun failed(
        current: AnalysisWorkflow,
        work: RetryWork,
        message: String,
        retryCount: Int,
    ): AnalysisWorkflow = AnalysisWorkflow(
        current.id,
        AnalysisWorkflowState.Failed(work, message, retryCount),
    ).also { store.save(it) }

    private fun queueOwnershipKey(workflowId: String): String = "analysis:$workflowId"

    private data class ProcessTarget(val taskId: String, val sessionId: String)
}
