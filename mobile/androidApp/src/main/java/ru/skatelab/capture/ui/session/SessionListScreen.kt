package ru.skatelab.capture.ui.session

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.shared.models.SessionResponse
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

    LaunchedEffect(Unit) {
        viewModel.loadSessions()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Результаты") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
            )
        },
    ) { padding ->
        when (uiState) {
            is SessionsUiState.Loading -> {
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    CircularProgressIndicator()
                    Spacer(modifier = Modifier.height(12.dp))
                    Text("Загрузка…", style = MaterialTheme.typography.bodyLarge)
                }
            }
            is SessionsUiState.Error -> {
                val message = (uiState as SessionsUiState.Error).message
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("Ошибка: $message", color = MaterialTheme.colorScheme.error)
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        "Потяните вниз, чтобы обновить",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            is SessionsUiState.Loaded -> {
                val loaded = uiState as SessionsUiState.Loaded
                val sessions = loaded.sessions

                PullToRefreshBox(
                    isRefreshing = isRefreshing,
                    onRefresh = {
                        isRefreshing = true
                        viewModel.refresh()
                    },
                    state = rememberPullToRefreshState(),
                    modifier = Modifier.padding(padding),
                ) {
                    if (sessions.isEmpty()) {
                        Column(
                            modifier = Modifier.fillMaxSize(),
                            verticalArrangement = Arrangement.Center,
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Text(
                                "Нет результатов анализа",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        LaunchedEffect(uiState) {
                            isRefreshing = false
                        }
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                                start = 16.dp,
                                end = 16.dp,
                                top = 8.dp,
                                bottom = 16.dp,
                            ),
                        ) {
                            items(sessions, key = { it.id }) { session ->
                                SessionCard(
                                    session = session,
                                    onClick = { onSessionClick(session.id) },
                                )
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
) {
    Card(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
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
                    text = formatElementType(session.elementType),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = formatDate(session.createdAt),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            StatusBadge(status = session.status, score = session.overallScore)
        }
    }
}

@Composable
private fun StatusBadge(status: String, score: Float?) {
    val (label, color) = when (status) {
        "completed" -> ("Готово" to MaterialTheme.colorScheme.primary)
        "processing" -> ("Обработка…" to MaterialTheme.colorScheme.tertiary)
        "failed" -> ("Ошибка" to MaterialTheme.colorScheme.error)
        "queued" -> ("В очереди" to MaterialTheme.colorScheme.outline)
        else -> (status to MaterialTheme.colorScheme.onSurfaceVariant)
    }

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        if (score != null && status == "completed") {
            Text(
                text = "%.0f%%".format(score * 100),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = color,
            )
        }
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = color,
        )
    }
}

private fun formatElementType(elementType: String): String {
    return when (elementType.lowercase()) {
        "axel" -> "Аксель"
        "lutz" -> "Лутц"
        "flip" -> "Флип"
        "loop" -> "Риттбергер"
        "salchow" -> "Сальхов"
        "toe_loop" -> "Тулуп"
        "toe_loop_flip" -> "Тулуп (флип)"
        "combination" -> "Каскад"
        else -> elementType.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}

private fun formatDate(isoDate: String): String {
    return try {
        val instant = java.time.Instant.parse(isoDate)
        val formatter = java.time.format.DateTimeFormatter
            .ofPattern("dd.MM.yyyy HH:mm")
            .withZone(java.time.ZoneId.systemDefault())
        formatter.format(instant)
    } catch (_: Exception) {
        isoDate
    }
}