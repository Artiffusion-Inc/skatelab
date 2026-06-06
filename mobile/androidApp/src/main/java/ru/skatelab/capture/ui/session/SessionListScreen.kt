package ru.skatelab.capture.ui.session

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.models.elementLabelRu
import ru.skatelab.shared.models.elementLabelsRu
import ru.skatelab.shared.state.SessionsUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionListScreen(
    viewModel: AndroidSessionsViewModel,
    onSessionClick: (String) -> Unit,
    onBack: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    var isRefreshing by remember { mutableStateOf(false) }
    var selectedElementType by remember { mutableStateOf<String?>(null) }
    val resultsTitle = stringResource(R.string.session_list_results)
    val navBackLabel = stringResource(R.string.session_list_nav_back)

    LaunchedEffect(Unit) {
        viewModel.loadSessions()
    }

    // Reset refresh flag when data loads or errors
    LaunchedEffect(uiState) {
        if (uiState !is SessionsUiState.Loading) {
            isRefreshing = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(resultsTitle) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = navBackLabel)
                    }
                },
            )
        },
    ) { padding ->
        when (uiState) {
            is SessionsUiState.Loading -> {
                val loadingLabel = stringResource(R.string.session_list_loading)
                val context = LocalContext.current
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box(
                        modifier =
                            Modifier
                                .semantics(mergeDescendants = true) {
                                    contentDescription = context.getString(R.string.cd_loading)
                                    role = Role.ValuePicker
                                },
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(48.dp))
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(loadingLabel, style = MaterialTheme.typography.bodyLarge)
                }
            }
            is SessionsUiState.Error -> {
                val errorLabel = stringResource(R.string.session_list_error)
                val retryLabel = stringResource(R.string.session_list_retry)
                val message = (uiState as SessionsUiState.Error).error.messageKey
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(errorLabel, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.error)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        message,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(onClick = { viewModel.loadSessions(elementType = selectedElementType) }) {
                        Text(retryLabel)
                    }
                }
            }
            is SessionsUiState.Loaded -> {
                val loaded = uiState as SessionsUiState.Loaded
                val sessions = loaded.sessions
                val emptyLabel = stringResource(R.string.session_list_empty)

                // Infinite scroll
                val listState = rememberLazyListState()
                LaunchedEffect(listState) {
                    snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index }
                        .collect { lastVisible ->
                            val total = sessions.size
                            if (lastVisible != null && lastVisible >= total - 2) {
                                viewModel.loadMore()
                            }
                        }
                }

                PullToRefreshBox(
                    isRefreshing = isRefreshing,
                    onRefresh = {
                        isRefreshing = true
                        viewModel.loadSessions(elementType = selectedElementType)
                    },
                    state = rememberPullToRefreshState(),
                    modifier = Modifier.padding(padding),
                ) {
                    Column(modifier = Modifier.fillMaxSize()) {
                        // Filter chips
                        Row(
                            modifier =
                                Modifier
                                    .fillMaxWidth()
                                    .horizontalScroll(rememberScrollState())
                                    .padding(horizontal = 16.dp, vertical = 8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            FilterChip(
                                selected = selectedElementType == null,
                                onClick = {
                                    selectedElementType = null
                                    viewModel.loadSessions(elementType = null)
                                },
                                label = { Text(stringResource(R.string.filter_all)) },
                            )
                            elementLabelsRu.forEach { (key, label) ->
                                FilterChip(
                                    selected = selectedElementType == key,
                                    onClick = {
                                        selectedElementType = key
                                        viewModel.loadSessions(elementType = key)
                                    },
                                    label = { Text(label) },
                                )
                            }
                        }

                        if (sessions.isEmpty()) {
                            Column(
                                modifier = Modifier.fillMaxSize(),
                                verticalArrangement = Arrangement.Center,
                                horizontalAlignment = Alignment.CenterHorizontally,
                            ) {
                                Text(
                                    emptyLabel,
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        } else {
                            LazyColumn(
                                state = listState,
                                modifier = Modifier.fillMaxSize().testTag("sessionListContent"),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                                contentPadding =
                                    androidx.compose.foundation.layout.PaddingValues(
                                        start = 16.dp,
                                        end = 16.dp,
                                        top = 0.dp,
                                        bottom = 16.dp,
                                    ),
                            ) {
                                items(sessions, key = { it.id }) { session ->
                                    SessionCard(
                                        session = session,
                                        onClick = { onSessionClick(session.id) },
                                    )
                                }
                                if (loaded.isLoadingMore) {
                                    item {
                                        Box(
                                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                                            contentAlignment = Alignment.Center,
                                        ) {
                                            CircularProgressIndicator(modifier = Modifier.size(32.dp))
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SessionCard(
    session: SessionResponse,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth().testTag("sessionCard"),
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
    ) {
        Row(
            modifier = Modifier.padding(12.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = session.elementType.elementLabelRu(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = formatDate(session.createdAt),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                // Inline metrics — show first 2
                val priorityMetrics =
                    session.metrics
                        .filter { it.metricName in listOf("airtime", "rotation_speed") }
                val displayMetrics =
                    priorityMetrics.ifEmpty {
                        session.metrics.take(2)
                    }.take(2)
                if (displayMetrics.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        displayMetrics.forEach { metric ->
                            Text(
                                text = "${metricLabelRu(metric.metricName)}: ${formatMetricValue(metric.metricValue)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
            StatusBadge(status = session.status, score = session.overallScore)
        }
    }
}

@Composable
private fun StatusBadge(
    status: String,
    score: Float?,
) {
    val (label, color) =
        when (status) {
            "completed" -> (stringResource(R.string.status_completed) to MaterialTheme.colorScheme.primary)
            "processing" -> (stringResource(R.string.status_processing) to MaterialTheme.colorScheme.tertiary)
            "failed" -> (stringResource(R.string.status_failed) to MaterialTheme.colorScheme.error)
            "queued" -> (stringResource(R.string.status_queued) to MaterialTheme.colorScheme.outline)
            else -> (status to MaterialTheme.colorScheme.onSurfaceVariant)
        }

    // GOE score badge with color coding
    val goeColor =
        when {
            score != null && status == "completed" && score >= 0.7f -> MaterialTheme.colorScheme.primary
            score != null && status == "completed" && score >= 0.4f -> MaterialTheme.colorScheme.tertiary
            score != null && status == "completed" -> MaterialTheme.colorScheme.error
            else -> color
        }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        if (score != null && status == "completed") {
            Text(
                text = "GOE %.0f%%".format(score * 100),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = goeColor,
            )
        }
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = color,
        )
    }
}

@Composable
private fun metricLabelRu(metricName: String): String =
    when (metricName) {
        "airtime" -> stringResource(R.string.metric_airtime_label)
        "rotation_speed" -> stringResource(R.string.metric_rotation_speed_label)
        "jump_height" -> stringResource(R.string.metric_jump_height_label)
        "knee_angle" -> stringResource(R.string.metric_knee_angle_label)
        "landing_quality" -> stringResource(R.string.metric_landing_quality_label)
        else -> metricName.replaceFirstChar { it.uppercase() }
    }

private fun formatMetricValue(value: Float): String {
    return if (value < 1 && value > -1) {
        "%.2f".format(value)
    } else {
        "%.1f".format(value)
    }
}

private fun formatDate(isoDate: String): String {
    return try {
        val instant = java.time.Instant.parse(isoDate)
        val formatter =
            java.time.format.DateTimeFormatter
                .ofPattern("dd.MM.yyyy HH:mm")
                .withZone(java.time.ZoneId.systemDefault())
        formatter.format(instant)
    } catch (_: Exception) {
        isoDate
    }
}
