package ru.skatelab.capture.presentation.sessiondetail

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.IosShare
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.ui.PlayerView
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberBottom
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberStart
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoScrollState
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoZoomState
import com.patrykandpatrick.vico.core.cartesian.axis.HorizontalAxis
import com.patrykandpatrick.vico.core.cartesian.axis.VerticalAxis
import com.patrykandpatrick.vico.core.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.ImuChartData
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionDetailScreen(
    viewModel: SessionDetailViewModel,
    sessionId: String,
    onBack: () -> Unit,
    onExport: (String) -> Unit,
) {
    val session by viewModel.session.collectAsState()
    val imuData by viewModel.imuData.collectAsState()
    val isImuLoading by viewModel.isImuLoading.collectAsState()
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf(
        stringResource(R.string.tab_video),
        stringResource(R.string.tab_charts),
        stringResource(R.string.tab_details),
    )

    LaunchedEffect(sessionId) {
        viewModel.loadSession(sessionId)
    }

    Column(modifier = Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text(stringResource(R.string.session_detail_title)) },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                }
            },
        )

        TabRow(selectedTabIndex = selectedTab) {
            tabs.forEachIndexed { index, title ->
                Tab(
                    selected = selectedTab == index,
                    onClick = {
                        selectedTab = index
                        if (index == 1) viewModel.loadImuData()
                    },
                    text = { Text(title) },
                )
            }
        }

        when (selectedTab) {
            0 -> VideoTab(viewModel)
            1 -> ChartsTab(imuData, isImuLoading, viewModel)
            2 -> DetailsTab(session, onExport = { session?.id?.let(onExport) })
        }
    }
}

@Composable
private fun VideoTab(viewModel: SessionDetailViewModel) {
    val context = LocalContext.current
    val session by viewModel.session.collectAsState()
    val exoPlayer = remember { viewModel.getPlayer(context) }

    LaunchedEffect(session?.id) {
        session?.let { viewModel.setVideoSource(exoPlayer) }
    }

    LaunchedEffect(exoPlayer) {
        while (true) {
            if (exoPlayer.isPlaying) {
                viewModel.updatePlaybackPosition(exoPlayer.currentPosition)
            }
            kotlinx.coroutines.delay(100L)
        }
    }

    AndroidView(
        factory = { ctx ->
            PlayerView(ctx).apply {
                player = exoPlayer
                useController = true
            }
        },
        modifier = Modifier.fillMaxSize(),
    )
}

@Composable
private fun ChartsTab(
    imuData: ImuChartData?,
    isLoading: Boolean,
    viewModel: SessionDetailViewModel,
) {
    val playbackPositionMs by viewModel.playbackPositionMs.collectAsState()

    when {
        isLoading -> {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        }
        imuData == null || imuData.timeSeconds.isEmpty() -> {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.imu_no_data))
            }
        }
        else -> {
            Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
                ImuChartSection(
                    label = stringResource(R.string.label_acc_mag),
                    timeSeconds = imuData.timeSeconds,
                    leftValues = imuData.accMagLeft,
                    rightValues = imuData.accMagRight,
                    playheadTime = if (imuData.timeSeconds.isNotEmpty()) playbackPositionMs / 1000f else null,
                )
                Spacer(modifier = Modifier.height(24.dp))
                ImuChartSection(
                    label = stringResource(R.string.label_ang_vel),
                    timeSeconds = imuData.timeSeconds,
                    leftValues = imuData.angVelLeft,
                    rightValues = imuData.angVelRight,
                    playheadTime = if (imuData.timeSeconds.isNotEmpty()) playbackPositionMs / 1000f else null,
                )
                Spacer(modifier = Modifier.height(24.dp))
                ImuChartSection(
                    label = stringResource(R.string.label_rotation),
                    timeSeconds = imuData.timeSeconds,
                    leftValues = imuData.rotLeft,
                    rightValues = imuData.rotRight,
                    playheadTime = if (imuData.timeSeconds.isNotEmpty()) playbackPositionMs / 1000f else null,
                )
            }
        }
    }
}

@Composable
private fun ImuChartSection(
    label: String,
    timeSeconds: FloatArray,
    leftValues: FloatArray,
    rightValues: FloatArray,
    playheadTime: Float? = null,
) {
    val modelProducer = remember { CartesianChartModelProducer() }
    LaunchedEffect(timeSeconds.contentHashCode(), leftValues.contentHashCode()) {
        modelProducer.runTransaction {
            lineSeries {
                series(timeSeconds.toList(), leftValues.toList())
                series(timeSeconds.toList(), rightValues.toList())
            }
        }
    }

    Column {
        Text(label, style = MaterialTheme.typography.titleSmall)
        Spacer(modifier = Modifier.height(8.dp))
        Box(modifier = Modifier.fillMaxWidth().height(200.dp)) {
            CartesianChartHost(
                chart = rememberCartesianChart(
                    rememberLineCartesianLayer(),
                    startAxis = VerticalAxis.rememberStart(),
                    bottomAxis = HorizontalAxis.rememberBottom(),
                ),
                modelProducer = modelProducer,
                modifier = Modifier.fillMaxSize(),
                scrollState = rememberVicoScrollState(),
                zoomState = rememberVicoZoomState(),
            )
            if (playheadTime != null && timeSeconds.isNotEmpty()) {
                val maxX = timeSeconds.last()
                if (maxX > 0f && playheadTime in 0f..maxX) {
                    val fraction = playheadTime / maxX
                    Canvas(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(start = (fraction * 200).dp),
                    ) {
                        drawLine(
                            color = Color.Red,
                            start = Offset(0f, 0f),
                            end = Offset(0f, size.height),
                            strokeWidth = 2f,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailsTab(
    session: CaptureSession?,
    onExport: () -> Unit,
) {
    if (session == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(stringResource(R.string.detail_duration, session.durationMs / 1000), style = MaterialTheme.typography.bodyLarge)
        Text(stringResource(R.string.detail_fps, session.actualFps), style = MaterialTheme.typography.bodyLarge)
        if (session.videoWidth > 0 && session.videoHeight > 0) {
            Text(stringResource(R.string.detail_resolution, session.videoWidth, session.videoHeight), style = MaterialTheme.typography.bodyLarge)
        }
        Text(
            stringResource(R.string.detail_fps_verified, if (session.fpsVerified) stringResource(R.string.detail_yes) else stringResource(R.string.detail_no)),
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            stringResource(R.string.detail_timestamp_source, session.timestampSource),
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            if (session.isComplete) stringResource(R.string.detail_status_complete)
            else stringResource(R.string.detail_status_incomplete),
            style = MaterialTheme.typography.bodyLarge,
            color = if (session.isComplete) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.error,
        )

        Spacer(modifier = Modifier.height(8.dp))
        Text("Файлы", style = MaterialTheme.typography.titleMedium)
        HorizontalDivider()
        Text(stringResource(R.string.detail_video_size, fileSizeLabel(session.videoFile)), style = MaterialTheme.typography.bodyMedium)
        Text(stringResource(R.string.detail_imu_left, fileSizeLabel(session.imuLeftFile)), style = MaterialTheme.typography.bodyMedium)
        Text(stringResource(R.string.detail_imu_right, fileSizeLabel(session.imuRightFile)), style = MaterialTheme.typography.bodyMedium)

        Spacer(modifier = Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(
                onClick = onExport,
                modifier = Modifier.weight(1f),
            ) {
                Icon(Icons.Default.IosShare, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text(stringResource(R.string.export_title))
            }
        }
    }
}

@Composable
private fun fileSizeLabel(file: File): String {
    return if (file.exists()) {
        val kb = file.length() / 1024.0
        stringResource(R.string.detail_file_present, file.name, kb)
    } else {
        stringResource(R.string.detail_file_absent)
    }
}