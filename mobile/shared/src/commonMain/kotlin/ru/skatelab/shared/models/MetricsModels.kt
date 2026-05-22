package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class MetricsRegistryResponse(
    val metrics: Map<String, MetricDefinition>
)

@Serializable
data class MetricDefinition(
    val name: String,
    @SerialName("label_ru") val labelRu: String? = null,
    val unit: String,
    val format: String? = null,
    val direction: String? = null,
    @SerialName("element_types") val elementTypes: List<String>? = null,
    @SerialName("ideal_range") val idealRange: Map<String, Double>? = null,
)

@Serializable
data class TrendResponse(
    @SerialName("metric_name") val metricName: String,
    @SerialName("element_type") val elementType: String,
    @SerialName("data_points") val dataPoints: List<TrendDataPoint>,
    val trend: String? = null,
    @SerialName("current_pr") val currentPr: Double? = null,
    @SerialName("reference_range") val referenceRange: Map<String, Double>? = null,
)

@Serializable
data class TrendDataPoint(
    @SerialName("session_id") val sessionId: String,
    val value: Double,
    @SerialName("is_pr") val isPr: Boolean = false,
    val date: String? = null,
)

@Serializable
data class PRsResponse(
    val prs: List<PersonalRecord>
)

@Serializable
data class PersonalRecord(
    @SerialName("element_type") val elementType: String? = null,
    @SerialName("metric_name") val metricName: String,
    val value: Double,
    @SerialName("session_id") val sessionId: String,
)

@Serializable
data class DiagnosticsResponse(
    @SerialName("user_id") val userId: String,
    val findings: List<DiagnosticsFinding>
)

@Serializable
data class DiagnosticsFinding(
    val severity: String,
    val element: String? = null,
    val metric: String? = null,
    val message: String,
    val detail: String? = null,
)

@Serializable
data class SummaryResponse(
    val element: String,
    val period: String,
    val trend: String? = null,
    val findings: List<DiagnosticsFinding>? = null,
    @SerialName("metric_defs") val metricDefs: Map<String, MetricDefinition>? = null,
    @SerialName("personal_records") val personalRecords: List<PersonalRecord>? = null,
)
