package ru.skatelab.capture.ui.upload

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadEntity

class UploadQueueScreenTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun uploadCard_ready_showsPreparingUpload() {
        val entity = PendingUploadEntity(
            id = "test-1",
            videoPath = "/data/test.mp4",
            status = "READY",
        )
        composeRule.setContent {
            UploadCard(
                entity = entity,
                onRetry = {},
                onCancel = {},
            )
        }
        composeRule.onNodeWithText("Preparing upload…").assertIsDisplayed()
    }

    @Test
    fun uploadCard_uploading_showsUploadingVideo() {
        val entity = PendingUploadEntity(
            id = "test-1",
            videoPath = "/data/test.mp4",
            status = "UPLOADING",
        )
        composeRule.setContent {
            UploadCard(
                entity = entity,
                onRetry = {},
                onCancel = {},
            )
        }
        composeRule.onNodeWithText("Uploading video…").assertIsDisplayed()
    }
}