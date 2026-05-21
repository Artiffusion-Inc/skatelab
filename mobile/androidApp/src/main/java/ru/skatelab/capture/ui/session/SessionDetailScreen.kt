package ru.skatelab.capture.ui.session

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberBottom
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberStart
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoScrollState
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoZoomState
import com.patrykandpatrick.vico.core.cartesian.Zoom
import com.patrykandpatrick.vico.core.cartesian.axis.HorizontalAxis
import com.patrykandpatrick.vico.core.cartesian.axis.VerticalAxis
import com.patrykandpatrick.vico.core.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries
import ru.skatelab.shared.models.SessionMetricResponse
import ru.skatelab.shared.models.SessionResponse
import ru.skatelab.shared.state.SessionsUiState
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SessionDetailScreen(
    viewModel: AndroidSessionsViewModel,
    sessionId: String,
    onBack: () -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val selectedSession by viewModel.selectedSession.collectAsState()

    LaunchedEffect(sessionId) {
        viewModel.loadSession(sessionId)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(selectedSession?.elementType?.let { formatElementType(it) } ?: "Результат")
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
            )
        },
    ) { padding ->
        when {
            uiState is SessionsUiState.Loading && selectedSession == null -> {
                Box(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
            selectedSession != null -> {
                SessionDetailContent(
                    session = selectedSession!!,
                    modifier = Modifier.padding(padding),
                )
            }
            uiState is SessionsUiState.Error -> {
                Box(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "Ошибка: ${(uiState as SessionsUiState.Error).message}",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SessionDetailContent(
    session: SessionResponse,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
    ) {
        // Video player
        session.processedVideoUrl?.let { videoUrl ->
            VideoPlayer(url = videoUrl)
            Spacer(modifier = Modifier.height(12.dp))
        } ?: session.videoUrl?.let { videoUrl ->
            VideoPlayer(url = videoUrl)
            Spacer(modifier = Modifier.height(12.dp))
        }

        Column(modifier = Modifier.padding(horizontal = 16.dp)) {
            // Element type badge
            ElementTypeBadge(elementType = session.elementType, status = session.status)
            Spacer(modifier = Modifier.height(16.dp))

            // Score
            session.overallScore?.let { score ->
                Row(
                    verticalAlignment = Alignment.Bottom,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(
                        text = "%.0f%%".format(score * 100),
                        style = MaterialTheme.typography.displaySmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = "оценка",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 6.dp),
                    )
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            // Metric cards grid
            if (session.metrics.isNotEmpty()) {
                Text(
                    text = "Метрики",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(8.dp))
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    session.metrics.forEach { metric ->
                        MetricCard(
                            metric = metric,
                            modifier = Modifier.weight(1f).padding(2.dp),
                        )
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            // Angular velocity chart (if metric has time-series data)
            val angularMetrics = session.metrics.filter {
                it.metricName == "angular_velocity"
            }
            if (angularMetrics.isNotEmpty()) {
                AngularVelocityChart(angularMetrics)
                Spacer(modifier = Modifier.height(16.dp))
            }

            // Recommendations
            val recommendations = session.recommendations
            if (!recommendations.isNullOrEmpty()) {
                Text(
                    text = "Рекомендации",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(8.dp))
                recommendations.forEach { rec ->
                    Card(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant,
                        ),
                    ) {
                        Text(
                            text = rec,
                            modifier = Modifier.padding(12.dp),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun VideoPlayer(url: String) {
    val context = LocalContext.current
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().also { player ->
            player.setMediaItem(MediaItem.fromUri(Uri.parse(url)))
            player.playWhenReady = true
            player.prepare()
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            exoPlayer.release()
        }
    }

    AndroidView(
        factory = { ctx ->
            android.view.LayoutInflater.from(ctx)
                .inflate(ru.skatelab.capture.R.layout.player_view_texture, null)
                .also { view ->
                    (view as? androidx.media3.ui.PlayerView)?.player = exoPlayer
                }
        },
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(16f / 9f),
    )
}

@Composable
private fun ElementTypeBadge(elementType: String, status: String) {
    val statusLabel = when (status) {
        "completed" -> "Готово"
        "processing" -> "Обработка…"
        "failed" -> "Ошибка"
        "queued" -> "В очереди"
        else -> status
    }
    val statusColor = when (status) {
        "completed" -> MaterialTheme.colorScheme.primary
        "processing" -> MaterialTheme.colorScheme.tertiary
        "failed" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Card(
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer,
            ),
        ) {
            Text(
                text = formatElementType(elementType),
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
        Text(
            text = statusLabel,
            style = MaterialTheme.typography.labelMedium,
            color = statusColor,
        )
    }
}

@Composable
private fun AngularVelocityChart(metrics: List<SessionMetricResponse>) {
    // If we have time-series data from the server, we'd plot it here.
    // For now, display a summary card since metrics are single values.
    // Future: when backend provides per-frame angular_velocity data,
    // render a Vico line chart here.
    val avgAngVel = metrics.map { it.metricValue }.average().toFloat()
    val maxAngVel = metrics.maxOf { it.metricValue }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant,
        ),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = "Угловая скорость",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    Text("Средняя", style = MaterialTheme.typography.labelSmall)
                    Text(
                        "%.1f °/с".format(avgAngVel),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Column {
                    Text("Максимальная", style = MaterialTheme.typography.labelSmall)
                    Text(
                        "%.1f °/с".format(maxAngVel),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
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
        "combination" -> "Каскад"
        else -> elementType.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}