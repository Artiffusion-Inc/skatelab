package ru.skatelab.capture.ui.processing

import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasProgressBarRangeInfo
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.state.ProcessingUiState

/**
 * Compose UI tests for ProcessingScreen composables.
 *
 * Tests run as instrumented tests (androidTest) because stringResource()
 * requires Android context. To run locally on Docker emulator:
 *   ./gradlew :androidApp:connectedDebugAndroidTest
 *   (or via Maestro CI pipeline)
 *
 * For JVM-level logic testing of state transitions, see
 * ProcessingViewModelTest in shared/commonTest.
 */
class ProcessingScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    // --- UploadStatusContent tests ---

    @Test
    fun uploadStatus_ready_showsPreparingUpload() {
        val entity =
            PendingUploadEntity(
                id = "test-1",
                videoPath = "/data/test.mp4",
                status = "READY",
            )
        composeRule.setContent {
            UploadStatusContent(entity = entity)
        }
        composeRule.onNodeWithText("Preparing upload…").assertIsDisplayed()
    }

    @Test
    fun uploadStatus_uploading_showsLinearProgress() {
        val entity =
            PendingUploadEntity(
                id = "test-1",
                videoPath = "/data/test.mp4",
                status = "UPLOADING",
            )
        composeRule.setContent {
            UploadStatusContent(entity = entity)
        }
        composeRule.onNodeWithTag("uploadProgress").assertIsDisplayed()
        composeRule.onNodeWithText("Uploading video…").assertIsDisplayed()
    }

    @Test
    fun uploadStatus_processing_showsStartingAnalysis() {
        val entity =
            PendingUploadEntity(
                id = "test-1",
                videoPath = "/data/test.mp4",
                status = "PROCESSING",
            )
        composeRule.setContent {
            UploadStatusContent(entity = entity)
        }
        composeRule.onNodeWithText("Starting analysis…").assertIsDisplayed()
    }

    // --- ProcessingContent tests ---

    @Test
    fun processing_idle_showsPreparing() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Idle,
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithText("Preparing…").assertIsDisplayed()
    }

    @Test
    fun processing_progress5_showsQueuing() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Progress(0.05f, ""),
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithText("Queuing…").assertIsDisplayed()
        composeRule.onNodeWithText("5%").assertIsDisplayed()
        composeRule.onNode(
            hasProgressBarRangeInfo(ProgressBarRangeInfo(0.05f, 0f..1f, 0)),
        ).assertIsDisplayed()
    }

    @Test
    fun processing_progress50_showsProcessingVideo() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Progress(0.5f, ""),
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithText("Processing video…").assertIsDisplayed()
        composeRule.onNodeWithText("50%").assertIsDisplayed()
        composeRule.onNode(
            hasProgressBarRangeInfo(ProgressBarRangeInfo(0.5f, 0f..1f, 0)),
        ).assertIsDisplayed()
        composeRule.onNodeWithText("Cancel").assertHasClickAction()
    }

    @Test
    fun processing_progress95_showsFinishing() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Progress(0.95f, ""),
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithText("Finishing up…").assertIsDisplayed()
        composeRule.onNodeWithText("95%").assertIsDisplayed()
    }

    @Test
    fun processing_failedNetwork_showsNoConnection() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Failed(AppError.Network()),
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithContentDescription("Error").assertIsDisplayed()
        composeRule.onNodeWithText("No connection").assertIsDisplayed()
        composeRule.onNodeWithText("Retry").assertHasClickAction()
        composeRule.onNodeWithText("Go back").assertHasClickAction()
    }

    @Test
    fun processing_failedServer_showsProcessingError() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Failed(AppError.Server()),
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithContentDescription("Error").assertIsDisplayed()
        composeRule.onNodeWithText("Processing error").assertIsDisplayed()
        composeRule.onNodeWithText("Retry").assertHasClickAction()
    }

    @Test
    fun processing_completed_showsDone() {
        composeRule.setContent {
            ProcessingContent(
                state = ProcessingUiState.Completed(sessionId = "session-1"),
                onRetry = {},
                onCancel = {},
                onBack = {},
            )
        }
        composeRule.onNodeWithText("Done!").assertIsDisplayed()
    }
}
