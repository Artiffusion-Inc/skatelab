package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionMetricResponse(
    val id: String,
    @SerialName("metric_name") val metricName: String,
    @SerialName("metric_value") val metricValue: Float,
    @SerialName("is_pr") val isPr: Boolean,
    @SerialName("prev_best") val prevBest: Float? = null,
    @SerialName("reference_value") val referenceValue: Float? = null,
    @SerialName("is_in_range") val isInRange: Boolean? = null,
)
