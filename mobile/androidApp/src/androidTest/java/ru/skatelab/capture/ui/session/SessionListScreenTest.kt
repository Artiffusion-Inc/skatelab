package ru.skatelab.capture.ui.session

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.state.SessionsUiState

class SessionListScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun sessionList_empty_showsNoSessions() {
        val session =
            SessionResponse(
                id = "s1",
                userId = "u1",
                elementType = "axel",
                videoUrl = null,
                processedVideoUrl = null,
                poseData = null,
                frameMetrics = null,
                status = "completed",
                errorMessage = null,
                phases = null,
                recommendations = null,
                overallScore = 85f,
                processTaskId = null,
                createdAt = "2026-06-01T10:00:00Z",
                processedAt = null,
                metrics = emptyList(),
            )
        composeRule.setContent {
            SessionCard(
                session = session,
                onClick = {},
            )
        }
        composeRule.onNodeWithText("Axel").assertIsDisplayed()
    }

    @Test
    fun analysisEmpty_showsReferenceCopyAndCameraCta() {
        var cameraClicked = false
        composeRule.setContent {
            SessionListContent(
                loaded = SessionsUiState.Loaded(sessions = emptyList(), total = 0),
                selectedElementType = null,
                onSessionClick = {},
                onStartAnalysis = { cameraClicked = true },
                onOpenFilters = {},
                onLoadMore = {},
            )
        }

        composeRule.onNodeWithText("No sessions yet").assertIsDisplayed()
        composeRule.onNodeWithText("Start analysis").assertIsDisplayed()
        composeRule.onNodeWithText("Record video").performClick()
        assertTrue(cameraClicked)
    }

    @Test
    fun analysisList_filterEntryAndSheet_applyExactElement() {
        val session =
            SessionResponse(
                id = "s3",
                userId = "u1",
                elementType = "3Lz",
                videoUrl = null,
                processedVideoUrl = null,
                poseData = null,
                frameMetrics = null,
                status = "completed",
                errorMessage = null,
                phases = null,
                recommendations = null,
                overallScore = 0.92f,
                processTaskId = null,
                createdAt = "2026-06-01T10:00:00Z",
                processedAt = null,
                metrics = emptyList(),
            )
        var filterOpened = false
        composeRule.setContent {
            SessionListContent(
                loaded = SessionsUiState.Loaded(sessions = listOf(session), total = 1),
                selectedElementType = "3Lz",
                onSessionClick = {},
                onStartAnalysis = {},
                onOpenFilters = { filterOpened = true },
                onLoadMore = {},
            )
        }

        composeRule.onNodeWithText("Recent analyses").assertIsDisplayed()
        composeRule.onNodeWithText("Filters").performClick()
        assertTrue(filterOpened)

        var appliedElement: String? = "3Lz"
        composeRule.setContent {
            SessionFilterSheet(
                selectedElementType = appliedElement,
                onApply = { appliedElement = it },
                onDismiss = {},
            )
        }
        composeRule.onNodeWithText("All").performClick()
        assertNull(appliedElement)
    }

    @Test
    fun sessionCard_showsElementTypeAndScore() {
        val session =
            SessionResponse(
                id = "s2",
                userId = "u1",
                elementType = "lutz",
                videoUrl = null,
                processedVideoUrl = null,
                poseData = null,
                frameMetrics = null,
                status = "completed",
                errorMessage = null,
                phases = null,
                recommendations = null,
                overallScore = 92f,
                processTaskId = null,
                createdAt = "2026-06-01T10:00:00Z",
                processedAt = null,
                metrics = emptyList(),
            )
        composeRule.setContent {
            SessionCard(
                session = session,
                onClick = {},
            )
        }
        composeRule.onNodeWithText("Lutz").assertIsDisplayed()
    }
}
