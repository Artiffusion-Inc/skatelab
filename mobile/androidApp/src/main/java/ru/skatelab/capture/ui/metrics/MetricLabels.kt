package ru.skatelab.capture.ui.metrics

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import ru.skatelab.capture.R

/**
 * Locale-aware metric display label (#406).
 *
 * Resolves a metric name (e.g. "airtime") to a localized label via `stringResource`,
 * mirroring the table in SessionListScreen. Use this instead of the backend `labelRu`
 * field so en-US users no longer see Russian ("Время полёта") or the raw metric name.
 */
@Composable
fun metricLabel(metricName: String): String =
    when (metricName) {
        "airtime" -> stringResource(R.string.metric_airtime_label)
        "rotation_speed" -> stringResource(R.string.metric_rotation_speed_label)
        "jump_height" -> stringResource(R.string.metric_jump_height_label)
        "knee_angle" -> stringResource(R.string.metric_knee_angle_label)
        "landing_quality" -> stringResource(R.string.metric_landing_quality_label)
        else -> metricName.replaceFirstChar { it.uppercase() }
    }
