package ru.skatelab.capture.ui.processing

import android.content.Context
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.api.IProcessApi
import ru.skatelab.shared.models.ProcessEvent
import ru.skatelab.shared.state.ProcessingUiState
import ru.skatelab.shared.state.ProcessingViewModel

@OptIn(ExperimentalCoroutinesApi::class)
class AndroidProcessingRestartTest {
    private val dispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun persistedProcessTaskId_isObservedAfterRestartWithoutQueueing() =
        runTest {
            val processApi = mockk<IProcessApi>()
            val dao = mockk<PendingUploadDao>()
            val entity =
                PendingUploadEntity(
                    id = "upload-1",
                    videoPath = File("video.mp4").path,
                    status = "PROCESSING",
                    videoKey = "videos/video.mp4",
                    sessionId = "session-1",
                    processTaskId = "task-1",
                )
            every { dao.getByIdFlow("upload-1") } returns flowOf(entity)
            every { processApi.stream("task-1") } returns
                flowOf(
                    ProcessEvent(
                        progress = 1f,
                        message = "Done",
                        status = "completed",
                        sessionId = "session-1",
                    ),
                )

            val viewModel =
                AndroidProcessingViewModel(
                    shared = ProcessingViewModel(processApi),
                    pendingUploadDao = dao,
                    appContext = mockk<Context>(relaxed = true),
                )

            val stateJob = launch { viewModel.processingState.collect() }
            viewModel.observeUpload("upload-1")
            advanceUntilIdle()
            assertTrue(viewModel.uploadPhase.value is UploadPhase.ReadyForProcessing)
            val ready = viewModel.uploadPhase.value as UploadPhase.ReadyForProcessing

            viewModel.startSseProcessing(ready.videoKey, ready.sessionId, ready.taskId)
            advanceUntilIdle()

            assertEquals(ProcessingUiState.Completed("session-1"), viewModel.processingState.value)
            coVerify(exactly = 1) { processApi.stream("task-1") }
            coVerify(exactly = 0) { processApi.queue(any(), any()) }
            stateJob.cancel()
        }
}
