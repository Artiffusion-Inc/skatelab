package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import ru.skatelab.shared.models.*

class MetricsApi(private val client: HttpClient) {
    suspend fun getRegistry(): MetricsRegistryResponse =
        client.get("/metrics/registry").body()

    suspend fun getTrend(metricName: String, period: String? = null): TrendResponse =
        client.get("/metrics/trend") {
            parameter("metric_name", metricName)
            if (period != null) parameter("period", period)
        }.body()

    suspend fun getPersonalRecords(): PRsResponse =
        client.get("/metrics/prs").body()

    suspend fun getDiagnostics(sessionId: String): DiagnosticsResponse =
        client.get("/metrics/diagnostics") {
            parameter("session_id", sessionId)
        }.body()

    suspend fun getSummary(elementType: String, period: String): SummaryResponse =
        client.get("/metrics/element-summary") {
            parameter("element_type", elementType)
            parameter("period", period)
        }.body()
}
