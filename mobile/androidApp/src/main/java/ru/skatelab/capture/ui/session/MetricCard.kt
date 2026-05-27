package ru.skatelab.capture.ui.session

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.EmojiEvents
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.mergeDescendants
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.models.SessionMetricResponse

/** Metric name → string resource ID for unit suffix. */
private val metricUnitResIds: Map<String, Int> =
    mapOf(
        "jump_height" to R.string.unit_m,
        "airtime" to R.string.unit_s,
        "angular_velocity" to R.string.unit_dps,
        "knee_angle_min" to R.string.unit_deg,
        "landing_quality" to 0,
        "rotation_count" to 0,
        "torso_lean" to R.string.unit_deg,
        "approach_arc" to 0,
        "pre_rotation" to R.string.unit_deg,
        "total_rotation" to R.string.unit_deg,
        "speed_at_takeoff" to R.string.unit_mps,
    )

@Composable
fun metricDisplayName(key: String): String =
    when (key) {
        "jump_height" -> stringResource(R.string.metric_jump_height)
        "airtime" -> stringResource(R.string.metric_airtime)
        "angular_velocity" -> stringResource(R.string.metric_angular_velocity)
        "knee_angle_min" -> stringResource(R.string.metric_knee_angle_min)
        "landing_quality" -> stringResource(R.string.metric_landing_quality)
        "rotation_count" -> stringResource(R.string.metric_rotation_count)
        "torso_lean" -> stringResource(R.string.metric_torso_lean)
        "approach_arc" -> stringResource(R.string.metric_approach_arc)
        "pre_rotation" -> stringResource(R.string.metric_pre_rotation)
        "total_rotation" -> stringResource(R.string.metric_total_rotation)
        "speed_at_takeoff" -> stringResource(R.string.metric_speed_at_takeoff)
        else -> key
    }

@Composable
fun MetricCard(
    metric: SessionMetricResponse,
    modifier: Modifier = Modifier,
) {
    val label = metricDisplayName(metric.metricName)
    val unitResId = metricUnitResIds[metric.metricName] ?: 0
    val unit = if (unitResId != 0) stringResource(unitResId) else ""

    Card(
        modifier = modifier.semantics(mergeDescendants = true) {}.padding(4.dp),
        colors =
            CardDefaults.cardColors(
                containerColor =
                    if (metric.isPr) {
                        MaterialTheme.colorScheme.primaryContainer
                    } else {
                        MaterialTheme.colorScheme.surfaceVariant
                    },
            ),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(
                    text = label,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (metric.isPr) {
                    Icon(
                        imageVector = Icons.Default.EmojiEvents,
                        contentDescription = "PR",
                        modifier = Modifier.size(24.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            Row(
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(
                    text = formatMetricValue(metric.metricValue),
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                if (unit.isNotEmpty()) {
                    Text(
                        text = unit,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 2.dp),
                    )
                }
            }
            ReferenceRange(metric)
        }
    }
}

@Composable
private fun ReferenceRange(metric: SessionMetricResponse) {
    val refValue = metric.referenceValue ?: return
    val inRange = metric.isInRange ?: return

    val rangeColor =
        if (inRange) {
            MaterialTheme.colorScheme.primary
        } else {
            MaterialTheme.colorScheme.error
        }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(
            text = stringResource(R.string.metric_reference),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = formatMetricValue(refValue),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = rangeColor,
        )
    }
}

private fun formatMetricValue(value: Float): String {
    return if (value >= 100) {
        "%.0f".format(value)
    } else if (value >= 1) {
        "%.1f".format(value)
    } else {
        "%.2f".format(value)
    }
}