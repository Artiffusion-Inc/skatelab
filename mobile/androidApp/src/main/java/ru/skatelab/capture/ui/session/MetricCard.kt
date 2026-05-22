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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.shared.models.SessionMetricResponse

/** Human-readable labels and units for known metric names. */
private val metricMeta: Map<String, Pair<String, String>> =
    mapOf(
        "jump_height" to ("Высота прыжка" to "м"),
        "airtime" to ("Время в воздухе" to "с"),
        "angular_velocity" to ("Угловая скорость" to "°/с"),
        "knee_angle_min" to ("Мин. угол колена" to "°"),
        "landing_quality" to ("Качество приземления" to ""),
        "rotation_count" to ("Количество вращений" to ""),
        "torso_lean" to ("Наклон корпуса" to "°"),
        "approach_arc" to ("Дуга разбега" to ""),
        "pre_rotation" to ("Предварит. вращение" to "°"),
        "total_rotation" to ("Общее вращение" to "°"),
        "speed_at_takeoff" to ("Скорость на отрыве" to "м/с"),
    )

@Composable
fun MetricCard(
    metric: SessionMetricResponse,
    modifier: Modifier = Modifier,
) {
    val meta = metricMeta[metric.metricName]
    val label = meta?.first ?: metric.metricName.replace('_', ' ').replaceFirstChar { it.uppercase() }
    val unit = meta?.second ?: ""

    Card(
        modifier = modifier.padding(4.dp),
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
                        modifier = Modifier.size(16.dp),
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
            text = "Референс:",
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
