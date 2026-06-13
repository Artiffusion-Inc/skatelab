package ru.skatelab.capture.ui.session

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test
import ru.skatelab.shared.models.SessionResponse

class SessionListScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun sessionList_empty_showsNoSessions() {
        val session = SessionResponse(
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
        composeRule.onNodeWithText("axel").assertIsDisplayed()
    }

    @Test
    fun sessionCard_showsElementTypeAndScore() {
        val session = SessionResponse(
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
        composeRule.onNodeWithText("lutz").assertIsDisplayed()
    }
}
