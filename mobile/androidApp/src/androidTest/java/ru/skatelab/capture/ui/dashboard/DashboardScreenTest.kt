package ru.skatelab.capture.ui.dashboard

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test
import ru.skatelab.shared.models.PersonalRecord
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.state.DashboardData

class DashboardScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun dashboard_empty_showsNoActiveProcessing() {
        val data =
            DashboardData(
                user = null,
                personalRecords = emptyList(),
                diagnostics = emptyList(),
                recentSessions = emptyList(),
                weeklySessions = emptyList(),
            )
        composeRule.setContent {
            DashboardContent(
                data = data,
                onNavigateToSessions = {},
                onNavigateToSessionDetail = {},
            )
        }
        composeRule.onNodeWithText("No active processing").assertIsDisplayed()
        composeRule.onNodeWithTag("dashboardContent").assertIsDisplayed()
    }

    @Test
    fun dashboard_withData_showsDashboardContent() {
        val personalRecords =
            listOf(
                PersonalRecord(elementType = "axel", value = 0.85, sessionId = "s1"),
            )
        val weeklySessions =
            listOf(
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
                ),
            )
        val data =
            DashboardData(
                user = null,
                personalRecords = personalRecords,
                diagnostics = emptyList(),
                recentSessions = emptyList(),
                weeklySessions = weeklySessions,
            )
        composeRule.setContent {
            DashboardContent(
                data = data,
                onNavigateToSessions = {},
                onNavigateToSessionDetail = {},
            )
        }
        composeRule.onNodeWithTag("dashboardContent").assertIsDisplayed()
    }
}
