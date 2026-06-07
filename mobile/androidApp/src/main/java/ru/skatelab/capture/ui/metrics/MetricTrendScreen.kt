package ru.skatelab.capture.ui.metrics

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberBottom
import com.patrykandpatrick.vico.compose.cartesian.axis.rememberStart
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.marker.rememberDefaultCartesianMarker
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoScrollState
import com.patrykandpatrick.vico.compose.cartesian.rememberVicoZoomState
import com.patrykandpatrick.vico.compose.common.component.rememberShapeComponent
import com.patrykandpatrick.vico.compose.common.component.rememberTextComponent
import com.patrykandpatrick.vico.core.cartesian.axis.HorizontalAxis
import com.patrykandpatrick.vico.core.cartesian.axis.VerticalAxis
import com.patrykandpatrick.vico.core.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries
import com.patrykandpatrick.vico.core.cartesian.decoration.HorizontalBox
import com.patrykandpatrick.vico.core.common.Fill
import com.patrykandpatrick.vico.core.common.shape.Shape
import ru.skatelab.capture.R
import ru.skatelab.shared.models.TrendDataPoint
import ru.skatelab.shared.models.TrendResponse
import ru.skatelab.shared.state.TrendState

private val ArcticSkySemi = Color(0x2629B6F6)
private val PrMarkerColor = Color(0xFFFFBF00)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MetricTrendScreen(
    viewModel: AndroidMetricTrendViewModel,
    metricName: String,
    elementType: String,
    onBack: () -> Unit,
) {
    val uiState by viewModel.shared.uiState.collectAsState()
    var selectedPeriod by remember { mutableStateOf("30d") }

    LaunchedEffect(metricName, elementType) {
        viewModel.shared.load(metricName, elementType)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(metricName) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.nav_back),
                        )
                    }
                },
            )
        },
    ) { padding ->
        when (val state = uiState) {
            is TrendState.Loading -> {
                val loadingDesc = stringResource(R.string.trend_loading_desc)
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box(
                        modifier =
                            Modifier
                                .semantics(mergeDescendants = true) {
                                    contentDescription = loadingDesc
                                    role = Role.ValuePicker
                                },
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(48.dp))
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(stringResource(R.string.session_list_loading), style = MaterialTheme.typography.bodyLarge)
                }
            }
            is TrendState.Error -> {
                Column(
                    modifier = Modifier.fillMaxSize().padding(padding),
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
                        state.error.messageKey,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(onClick = { viewModel.shared.load(metricName, elementType) }) {
                        Text(stringResource(R.string.session_list_retry))
                    }
                }
            }
            is TrendState.Loaded -> {
                val trend = state.trend
                val metricDef = state.metricDef

                Column(
                    modifier =
                        Modifier
                            .fillMaxSize()
                            .padding(padding)
                            .verticalScroll(rememberScrollState()),
                ) {
                    // Trend indicator row
                    TrendIndicatorRow(
                        label = metricDef.labelRu ?: metricName,
                        unit = metricDef.unit,
                        trendDirection = trend.trend,
                        currentPr = trend.currentPr,
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Period selector
                    PeriodSelectorRow(
                        selectedPeriod = selectedPeriod,
                        onPeriodChange = { period ->
                            selectedPeriod = period
                            viewModel.shared.changePeriod(metricName, elementType, period)
                        },
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Line chart
                    TrendChart(
                        trend = trend,
                        modifier = Modifier.fillMaxWidth().height(250.dp),
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Data table
                    DataTable(
                        dataPoints = trend.dataPoints,
                        unit = metricDef.unit,
                    )
                }
            }
        }
    }
}

@Composable
private fun TrendIndicatorRow(
    label: String,
    unit: String,
    trendDirection: String?,
    currentPr: Double?,
) {
    val (arrow, color) =
        when (trendDirection) {
            "improving" -> "↑" to Color(0xFF4CAF50)
            "declining" -> "↓" to Color(0xFFF44336)
            "stable" -> "→" to Color(0xFF9E9E9E)
            else -> "—" to Color(0xFF9E9E9E)
        }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant,
            ),
    ) {
        Row(
            modifier = Modifier.padding(16.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = label,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                if (unit.isNotBlank()) {
                    Text(
                        text = unit,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = arrow,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = color,
                )
                Spacer(modifier = Modifier.width(8.dp))
                if (currentPr != null) {
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            text = String.format("%.1f", currentPr),
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = stringResource(R.string.trend_current_pr),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PeriodSelectorRow(
    selectedPeriod: String,
    onPeriodChange: (String) -> Unit,
) {
    val periods =
        listOf(
        "30d" to stringResource(R.string.trend_period_30d),
        "90d" to stringResource(R.string.trend_period_90d),
        "all" to stringResource(R.string.trend_period_all),
    )

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        periods.forEach { (value, label) ->
            FilterChip(
                selected = value == selectedPeriod,
                onClick = { onPeriodChange(value) },
                label = { Text(label) },
            )
        }
    }
}

@Composable
private fun TrendChart(
    trend: TrendResponse,
    modifier: Modifier = Modifier,
) {
    val modelProducer = remember { CartesianChartModelProducer() }

    LaunchedEffect(trend.dataPoints) {
        val values = trend.dataPoints.map { it.value.toFloat() }
        if (values.isNotEmpty()) {
            modelProducer.runTransaction {
                lineSeries {
                    series(values)
                }
            }
        }
    }

    val prIndices =
        remember(trend.dataPoints) {
            trend.dataPoints.mapIndexedNotNull { i, dp -> if (dp.isPr) i else null }
        }

    val decorations =
        listOfNotNull(
            trend.referenceRange?.let { range ->
                val minY = range["min"] ?: 0.0
                val maxY = range["max"] ?: 100.0
                HorizontalBox(
                    y = { minY..maxY },
                    box =
                        rememberShapeComponent(
                            fill = Fill(ArcticSkySemi.value.toInt()),
                            shape = Shape.Rectangle,
                        ),
                )
            },
        )

    val prMarker = rememberDefaultCartesianMarker(label = rememberTextComponent())

    CartesianChartHost(
        modelProducer = modelProducer,
        chart =
            rememberCartesianChart(
                rememberLineCartesianLayer(),
                decorations = decorations,
                persistentMarkers =
                    if (prIndices.isEmpty()) {
                        null
                    } else {
                        { prIndices.forEach { index -> prMarker at index.toFloat() } }
                    },
                startAxis = VerticalAxis.rememberStart(),
                bottomAxis = HorizontalAxis.rememberBottom(),
            ),
        modifier = modifier,
        scrollState = rememberVicoScrollState(scrollEnabled = true),
        zoomState = rememberVicoZoomState(zoomEnabled = false),
    )
}

@Composable
private fun DataTable(
    dataPoints: List<TrendDataPoint>,
    unit: String,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        // Header
        Row(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(stringResource(R.string.trend_date_column), style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
            Text(stringResource(R.string.trend_value_column), style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
            Text("Δ", style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
            Spacer(modifier = Modifier.width(40.dp))
        }

        LazyColumn(
            modifier = Modifier.fillMaxWidth().height(300.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            itemsIndexed(dataPoints) { index, point ->
                val delta = if (index > 0) point.value - dataPoints[index - 1].value else null
                val deltaColor =
                    when {
                        delta == null -> MaterialTheme.colorScheme.onSurfaceVariant
                        delta > 0 -> Color(0xFF4CAF50)
                        delta < 0 -> Color(0xFFF44336)
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    }

                Row(
                    modifier =
                        Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = point.date ?: "—",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.weight(1f),
                    )
                    Text(
                        text = "${String.format("%.1f", point.value)} $unit",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.weight(1f),
                    )
                    Text(
                        text =
                            delta?.let {
                                "${if (it >= 0) "+" else ""}${String.format("%.1f", it)}"
                            }
                                ?: "—",
                        style = MaterialTheme.typography.bodyMedium,
                        color = deltaColor,
                        modifier = Modifier.weight(1f),
                    )
                    if (point.isPr) {
                        Text(
                            text = stringResource(R.string.trend_pr_marker),
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = PrMarkerColor,
                        )
                    } else {
                        Spacer(modifier = Modifier.width(40.dp))
                    }
                }
            }
        }
    }
}
