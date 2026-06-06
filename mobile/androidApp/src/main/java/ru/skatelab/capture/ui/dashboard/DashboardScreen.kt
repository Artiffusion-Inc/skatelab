package ru.skatelab.capture.ui.dashboard

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.models.DiagnosticsFinding
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.elementLabelRu
import ru.skatelab.shared.state.DashboardData
import ru.skatelab.shared.state.DashboardState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    viewModel: AndroidDashboardViewModel,
    onNavigateToSessions: (String?) -> Unit,
    onNavigateToSessionDetail: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.shared.uiState.collectAsState()
    var isRefreshing by remember { mutableStateOf(false) }

    LaunchedEffect(uiState) {
        if (uiState !is DashboardState.Loading) {
            isRefreshing = false
        }
    }

    when (uiState) {
        is DashboardState.Loading -> {
            Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                CircularProgressIndicator(modifier = Modifier.size(48.dp))
                Spacer(modifier = Modifier.height(12.dp))
                Text(stringResource(R.string.session_list_loading), style = MaterialTheme.typography.bodyLarge)
            }
        }
        is DashboardState.Error -> {
            val error = (uiState as DashboardState.Error).error
            Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    stringResource(R.string.session_list_error),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.error,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    error.messageKey,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(modifier = Modifier.height(16.dp))
                Button(onClick = { viewModel.shared.load() }) {
                    Text(stringResource(R.string.session_list_retry))
                }
            }
        }
        is DashboardState.Loaded -> {
            val data = (uiState as DashboardState.Loaded).data
            PullToRefreshBox(
                isRefreshing = isRefreshing,
                onRefresh = {
                    isRefreshing = true
                    viewModel.shared.load()
                },
                state = rememberPullToRefreshState(),
            ) {
                DashboardContent(
                    data = data,
                    onNavigateToSessions = onNavigateToSessions,
                    onNavigateToSessionDetail = onNavigateToSessionDetail,
                    modifier = modifier,
                )
            }
        }
    }
}

@Composable
private fun DashboardContent(
    data: DashboardData,
    onNavigateToSessions: (String?) -> Unit,
    onNavigateToSessionDetail: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                .fillMaxSize()
                .padding(16.dp)
                .testTag("dashboardContent"),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // Greeting
        val name = data.user?.displayName
        Text(
            text = if (name != null) stringResource(R.string.dashboard_greeting_name, name) else stringResource(R.string.dashboard_greeting),
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )

        // Best Results
        if (data.personalRecords.isNotEmpty()) {
            Text(
                text = stringResource(R.string.dashboard_best_results),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            val prByType =
                data.personalRecords
                    .filter { it.elementType != null }
                    .groupBy { it.elementType!! }
                    .mapValues { (_, records) -> records.maxByOrNull { it.value } }
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(prByType.entries.toList(), key = { it.key }) { (elementType, pr) ->
                    pr?.let { record ->
                        PrCard(
                            elementType = elementType!!,
                            score = record.value,
                            onClick = { onNavigateToSessions(elementType) },
                        )
                    }
                }
            }
        }

        // Weekly Summary
        if (data.weeklySessions.isNotEmpty()) {
            val completedWeekly = data.weeklySessions.filter { it.status == "completed" }
            val avgScore =
                completedWeekly
                    .mapNotNull { it.overallScore }
                    .takeIf { it.isNotEmpty() }
                    ?.let { scores -> scores.sum() / scores.size }
            ElevatedCard(
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.dashboard_week),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column {
                            Text(
                                text = stringResource(R.string.dashboard_sessions_count),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                text = "${data.weeklySessions.size}",
                                style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        if (avgScore != null) {
                            Column(horizontalAlignment = Alignment.End) {
                                Text(
                                    text = stringResource(R.string.dashboard_avg_score),
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                Text(
                                    text = "%.0f%%".format(avgScore * 100),
                                    style = MaterialTheme.typography.headlineSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = scoreColor(avgScore),
                                )
                            }
                        }
                    }
                }
            }
        }

        // Top Findings
        if (data.diagnostics.isNotEmpty()) {
            Text(
                text = stringResource(R.string.dashboard_recommendations),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            data.diagnostics.take(3).forEach { finding ->
                FindingRow(finding = finding)
            }
        }

        // Recent Sessions
        if (data.recentSessions.isNotEmpty()) {
            Text(
                text = stringResource(R.string.dashboard_recent_sessions),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            data.recentSessions.take(3).forEach { session ->
                RecentSessionRow(
                    session = session,
                    onClick = { onNavigateToSessionDetail(session.id) },
                )
            }
            TextButton(
                onClick = { onNavigateToSessions(null) },
                modifier = Modifier.align(Alignment.End),
            ) {
                Text(stringResource(R.string.dashboard_all_sessions))
            }
        }
    }
}

@Composable
private fun PrCard(
    elementType: String,
    score: Double,
    onClick: () -> Unit,
) {
    ElevatedCard(onClick = onClick) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = elementType.elementLabelRu(),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "%.0f%%".format(score * 100),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = scoreColor(score.toFloat()),
            )
        }
    }
}

@Composable
private fun FindingRow(finding: DiagnosticsFinding) {
    val icon =
        when (finding.severity) {
            "warning" -> "⚠️"
            "info" -> "💡"
            else -> "ℹ️"
        }
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text = icon, style = MaterialTheme.typography.titleMedium)
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = finding.message,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun RecentSessionRow(
    session: SessionResponse,
    onClick: () -> Unit,
) {
    ElevatedCard(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.padding(12.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = session.elementType.elementLabelRu(),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = formatDate(session.createdAt),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            session.overallScore?.let { score ->
                Text(
                    text = "%.0f%%".format(score * 100),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = scoreColor(score),
                )
            }
        }
    }
}

@Composable
private fun scoreColor(score: Float): androidx.compose.ui.graphics.Color {
    return when {
        score >= 0.7f -> MaterialTheme.colorScheme.primary
        score >= 0.4f -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.error
    }
}

private fun formatDate(isoDate: String): String {
    return try {
        val instant = java.time.Instant.parse(isoDate)
        val formatter =
            java.time.format.DateTimeFormatter
                .ofPattern("dd.MM.yyyy")
                .withZone(java.time.ZoneId.systemDefault())
        formatter.format(instant)
    } catch (_: Exception) {
        isoDate
    }
}
