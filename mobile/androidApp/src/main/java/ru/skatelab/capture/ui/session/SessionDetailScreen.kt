package ru.skatelab.capture.ui.session

import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.isActive
import ru.skatelab.capture.R
import ru.skatelab.capture.ui.skeleton.DynamicSkeletonOverlay
import ru.skatelab.shared.models.elementLabelRu
import ru.skatelab.shared.state.SessionDetailState

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SessionDetailScreen(
    viewModel: AndroidSessionDetailViewModel,
    sessionId: String,
    onBack: () -> Unit,
    onNavigateToMetricTrend: (metricName: String, elementType: String) -> Unit,
) {
    val uiState by viewModel.shared.uiState.collectAsState()

    LaunchedEffect(sessionId) {
        viewModel.shared.load(sessionId)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    val title =
                        (uiState as? SessionDetailState.Loaded)
                            ?.session?.elementType?.elementLabelRu()
                            ?: stringResource(R.string.session_detail_result_fallback)
                    Text(title)
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.session_ui_nav_back),
                        )
                    }
                },
            )
        },
    ) { padding ->
        when (val state = uiState) {
            is SessionDetailState.Loading -> {
                Box(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator()
                }
            }
            is SessionDetailState.Error -> {
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        stringResource(R.string.session_ui_error_loading),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.error,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        state.error.messageKey,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(onClick = { viewModel.shared.load(sessionId) }) {
                        Text(stringResource(R.string.session_ui_retry))
                    }
                }
            }
            is SessionDetailState.Loaded -> {
                SessionDetailContent(
                    state = state,
                    onToggleSkeleton = { viewModel.shared.toggleSkeleton() },
                    onNavigateToMetricTrend = onNavigateToMetricTrend,
                    modifier = Modifier.padding(padding),
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SessionDetailContent(
    state: SessionDetailState.Loaded,
    onToggleSkeleton: () -> Unit,
    onNavigateToMetricTrend: (metricName: String, elementType: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val session = state.session
    val showSkeleton = state.showSkeleton
    val context = LocalContext.current

    // ExoPlayer lifecycle
    val exoPlayer = remember { ExoPlayer.Builder(context).build() }
    val videoUrl = session.processedVideoUrl ?: session.videoUrl
    if (videoUrl != null) {
        LaunchedEffect(videoUrl) {
            exoPlayer.setMediaItem(MediaItem.fromUri(Uri.parse(videoUrl)))
            exoPlayer.playWhenReady = true
            exoPlayer.prepare()
        }
    }
    DisposableEffect(Unit) {
        onDispose { exoPlayer.release() }
    }

    // Track playback position and video dimensions for skeleton overlay
    var currentFrameMs by remember { mutableStateOf(0L) }
    var videoWidth by remember { mutableStateOf(1920) }
    var videoHeight by remember { mutableStateOf(1080) }
    LaunchedEffect(exoPlayer) {
        while (isActive) {
            if (exoPlayer.isPlaying || exoPlayer.currentPosition > 0) {
                currentFrameMs = exoPlayer.currentPosition
            }
            val format = exoPlayer.videoFormat
            if (format != null) {
                videoWidth = format.width
                videoHeight = format.height
            }
            kotlinx.coroutines.delay(50)
        }
    }

    // Recommendations collapse state
    var recommendationsExpanded by remember { mutableStateOf(false) }

    Column(
        modifier =
            modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
    ) {
        // -- Video player with skeleton overlay --
        if (videoUrl != null) {
            Box(
                modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
            ) {
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            player = exoPlayer
                        }
                    },
                    modifier = Modifier.matchParentSize(),
                )
                // Skeleton overlay
                session.poseData?.let { poseData ->
                    DynamicSkeletonOverlay(
                        poseData = poseData,
                        currentFrameMs = currentFrameMs,
                        phases = session.phases,
                        videoWidth = videoWidth,
                        videoHeight = videoHeight,
                        showOverlay = showSkeleton,
                        modifier = Modifier.matchParentSize(),
                    )
                }
                // Skeleton toggle FAB
                FloatingActionButton(
                    onClick = onToggleSkeleton,
                    modifier =
                        Modifier
                            .align(Alignment.BottomEnd)
                            .padding(8.dp),
                    containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.8f),
                ) {
                    Icon(
                        imageVector = if (showSkeleton) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                        contentDescription =
                            if (showSkeleton) {
                                stringResource(R.string.session_ui_hide_skeleton)
                            } else {
                                stringResource(R.string.session_ui_show_skeleton)
                            },
                    )
                }
            }
            Spacer(modifier = Modifier.height(12.dp))
        }

        Column(modifier = Modifier.padding(horizontal = 16.dp)) {
            // -- Phase timeline --
            val phases = session.phases
            if (phases != null) {
                PhaseTimeline(
                    phases = phases,
                    modifier = Modifier.fillMaxWidth().height(32.dp),
                )
                Spacer(modifier = Modifier.height(16.dp))
            }

            // -- GOE score --
            session.overallScore?.let { score ->
                Row(
                    verticalAlignment = Alignment.Bottom,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = "%.1f".format(score),
                        style = MaterialTheme.typography.displayMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = session.elementType.elementLabelRu(),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            // -- Metric cards grid --
            if (session.metrics.isNotEmpty()) {
                Text(
                    text = stringResource(R.string.session_ui_metrics_title),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(modifier = Modifier.height(8.dp))
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                    maxItemsInEachRow = 2,
                ) {
                    session.metrics.forEach { metric ->
                        val label =
                            state.metricDefs[metric.metricName]?.labelRu
                                ?: metric.metricName
                        MetricCard(
                            metric = metric,
                            label = label,
                            modifier =
                                Modifier
                                    .weight(1f)
                                    .padding(2.dp)
                                    .clickable {
                                        onNavigateToMetricTrend(
                                            metric.metricName,
                                            session.elementType,
                                        )
                                    },
                        )
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            // -- Recommendations (collapsible) --
            val recommendations = session.recommendations
            if (!recommendations.isNullOrEmpty()) {
                Row(
                    modifier =
                        Modifier
                            .fillMaxWidth()
                            .clickable { recommendationsExpanded = !recommendationsExpanded },
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = stringResource(R.string.session_ui_recommendations_title),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Icon(
                        imageVector =
                            if (recommendationsExpanded) {
                                Icons.Filled.ExpandLess
                            } else {
                                Icons.Filled.ExpandMore
                            },
                        contentDescription =
                            if (recommendationsExpanded) {
                                stringResource(R.string.session_ui_recommendations_collapse)
                            } else {
                                stringResource(R.string.session_ui_recommendations_expand)
                            },
                    )
                }
                AnimatedVisibility(visible = recommendationsExpanded) {
                    Column {
                        Spacer(modifier = Modifier.height(8.dp))
                        recommendations.forEach { rec ->
                            Card(
                                modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                                colors =
                                    CardDefaults.cardColors(
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
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

/** Phase timeline — thin horizontal bar with markers at takeoff/peak/landing frames. */
@Composable
private fun PhaseTimeline(
    phases: ru.skatelab.shared.models.PhasesData,
    modifier: Modifier = Modifier,
) {
    val markerColor = MaterialTheme.colorScheme.primary
    val lineColor = MaterialTheme.colorScheme.outlineVariant

    // Collect non-null markers with their normalized positions and labels.
    // We need a max frame to normalize — use the latest non-null phase frame as max.
    val markers =
        buildList {
            phases.takeoff?.let { add(it to stringResource(R.string.phase_takeoff)) }
            phases.peak?.let { add(it to stringResource(R.string.phase_peak)) }
            phases.landing?.let { add(it to stringResource(R.string.phase_landing)) }
        }

    if (markers.isEmpty()) return

    val maxFrame = markers.maxOf { it.first }.toFloat().coerceAtLeast(1f)

    Canvas(modifier = modifier.fillMaxWidth()) {
        val w = size.width
        val y = size.height / 2f

        // Base line
        drawLine(
            color = lineColor,
            start = Offset(0f, y),
            end = Offset(w, y),
            strokeWidth = 2f,
        )

        // Phase markers
        for ((frame, _) in markers) {
            val x = (frame.toFloat() / maxFrame) * w
            // Vertical tick
            drawLine(
                color = markerColor,
                start = Offset(x, y - 10f),
                end = Offset(x, y + 10f),
                strokeWidth = 2f,
            )
            // Dot
            drawCircle(
                color = markerColor,
                radius = 4f,
                center = Offset(x, y),
            )
        }
    }
}
