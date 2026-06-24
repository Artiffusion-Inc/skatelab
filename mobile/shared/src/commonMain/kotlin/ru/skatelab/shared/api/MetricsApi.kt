package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import ru.skatelab.shared.models.*
import ru.skatelab.shared.utils.expectSuccess

class MetricsApi(private val client: HttpClient) {
    suspend fun getRegistry(): MetricsRegistryResponse =
        client.get("metrics/registry").expectSuccess().body()

    suspend fun getTrend(metricName: String, elementType: String, period: String? = null): TrendResponse =
        client.get("metrics/trend") {
            parameter("metric_name", metricName)
            parameter("element_type", elementType)
            if (period != null) parameter("period", period)
        }.expectSuccess().body()

    suspend fun getPersonalRecords(): PRsResponse =
        client.get("metrics/prs").expectSuccess().body()

    suspend fun getDiagnostics(sessionId: String? = null): DiagnosticsResponse =
        client.get("metrics/diagnostics") {
            if (sessionId != null) parameter("session_id", sessionId)
        }.expectSuccess().body()

    suspend fun getSummary(elementType: String, period: String): SummaryResponse =
        client.get("metrics/element-summary") {
            parameter("element_type", elementType)
            parameter("period", period)
        }.expectSuccess().body()
}