package ru.skatelab.shared.models

import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import ru.skatelab.shared.api.PresignResponse
import ru.skatelab.shared.models.MetricsRegistryResponse
import ru.skatelab.shared.models.MetricDefinition
import ru.skatelab.shared.models.TrendResponse
import ru.skatelab.shared.models.TrendDataPoint
import ru.skatelab.shared.models.PRsResponse
import ru.skatelab.shared.models.PersonalRecord
import ru.skatelab.shared.models.DiagnosticsResponse
import ru.skatelab.shared.models.DiagnosticsFinding
import ru.skatelab.shared.models.SummaryResponse
import ru.skatelab.shared.models.SessionUpdateRequest
import kotlin.test.Test
import kotlin.test.assertEquals

class SerializationTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun tokenResponseRoundtrip() {
        val original = TokenResponse(
            accessToken = "abc123",
            refreshToken = "def456",
            tokenType = "bearer",
        )
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<TokenResponse>(encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun sessionMetricResponseDeserialize() {
        val payload = """{"id":"m1","metric_name":"jump_height","metric_value":45.2,"is_pr":false,"prev_best":null,"reference_value":50.0,"is_in_range":true}"""
        val decoded = json.decodeFromString<SessionMetricResponse>(payload)
        assertEquals("jump_height", decoded.metricName)
        assertEquals(45.2f, decoded.metricValue)
    }

    @Test
    fun processEventDeserialize() {
        val payload = """{"progress":0.7,"message":"GPU processing complete","status":"running"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(0.7f, decoded.progress)
        assertEquals(ProcessStatus.RUNNING, decoded.parsedStatus)
    }

    @Test
    fun sessionResponseRoundtrip() {
        val original = SessionResponse(
            id = "s1",
            userId = "u1",
            elementType = "axel",
            videoUrl = "https://r2.example.com/video.mp4",
            processedVideoUrl = null,
            status = "completed",
            overallScore = 87.5f,
            recommendations = listOf("Keep shoulders aligned", "Deeper knee bend"),
            metrics = emptyList(),
            createdAt = "2026-05-24T10:00:00Z",
        )
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<SessionResponse>(encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun sessionListResponseDeserialize() {
        val payload = """{"sessions":[{"id":"s1","user_id":"u1","element_type":"lutz","video_url":null,"processed_video_url":null,"status":"processing","overall_score":null,"recommendations":null,"metrics":[],"created_at":"2026-05-24T10:00:00Z"}],"total":1,"page":1,"page_size":20,"pages":1}"""
        val decoded = json.decodeFromString<SessionListResponse>(payload)
        assertEquals(1, decoded.total)
        assertEquals(1, decoded.page)
        assertEquals(20, decoded.pageSize)
        assertEquals(1, decoded.sessions.size)
        assertEquals("s1", decoded.sessions[0].id)
        assertEquals("u1", decoded.sessions[0].userId)
        assertEquals("lutz", decoded.sessions[0].elementType)
    }

    @Test
    fun uploadInitResponseDeserialize() {
        val payload = """{"upload_id":"up1","key":"videos/u1/vid.mp4","chunk_size":8388608,"part_count":3,"parts":[{"part_number":1,"url":"https://r2.example.com/p1"},{"part_number":2,"url":"https://r2.example.com/p2"},{"part_number":3,"url":"https://r2.example.com/p3"}]}"""
        val decoded = json.decodeFromString<UploadInitResponse>(payload)
        assertEquals("up1", decoded.uploadId)
        assertEquals("videos/u1/vid.mp4", decoded.key)
        assertEquals(8388608, decoded.chunkSize)
        assertEquals(3, decoded.partCount)
        assertEquals(3, decoded.parts.size)
        assertEquals(1, decoded.parts[0].partNumber)
        assertEquals("https://r2.example.com/p1", decoded.parts[0].url)
    }

    @Test
    fun userResponseRoundtrip() {
        val original = UserResponse(
            id = "u1",
            email = "skater@example.com",
            displayName = "Alice",
            avatarUrl = null,
            bio = "Figure skater",
            heightCm = 165.0,
            weightKg = 52.0,
            language = "ru",
            timezone = "Europe/Moscow",
            theme = "dark",
            onboardingRole = "athlete",
            angularUnit = "deg_per_sec",
        )
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<UserResponse>(encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun presignResponseDeserialize() {
        val payload = """{"url":"https://r2.example.com/presign?x-id=PutObject","key":"videos/u1/small.mp4"}"""
        val decoded = json.decodeFromString<PresignResponse>(payload)
        assertEquals("https://r2.example.com/presign?x-id=PutObject", decoded.url)
        assertEquals("videos/u1/small.mp4", decoded.key)
    }

    @Test
    fun sessionUpdateRequestRoundtrip() {
        val original = SessionUpdateRequest(elementType = "axel", notes = "PR attempt")
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<SessionUpdateRequest>(encoded)
        assertEquals("axel", decoded.elementType)
        assertEquals("PR attempt", decoded.notes)
    }

    @Test
    fun metricsRegistryResponseDeserialize() {
        val payload = """{"metrics":{"jump_height":{"name":"jump_height","label_ru":"Высота","unit":"cm","format":"%.1f","direction":"higher_is_better","element_types":["axel"],"ideal_range":{"min":30.0,"max":60.0}}}}"""
        val decoded = json.decodeFromString<MetricsRegistryResponse>(payload)
        assertEquals(1, decoded.metrics.size)
        assertEquals("jump_height", decoded.metrics["jump_height"]!!.name)
        assertEquals("cm", decoded.metrics["jump_height"]!!.unit)
    }

    @Test
    fun trendResponseDeserialize() {
        val payload = """{"metric_name":"jump_height","element_type":"axel","data_points":[{"session_id":"s1","value":45.2,"is_pr":true,"date":"2026-05-01"}],"trend":"improving","current_pr":45.2,"reference_range":{"min":30.0,"max":60.0}}"""
        val decoded = json.decodeFromString<TrendResponse>(payload)
        assertEquals("jump_height", decoded.metricName)
        assertEquals(1, decoded.dataPoints.size)
        assertEquals(45.2, decoded.dataPoints[0].value)
        assertEquals("improving", decoded.trend)
    }

    @Test
    fun prsResponseDeserialize() {
        val payload = """{"prs":[{"element_type":"axel","metric_name":"jump_height","value":45.2,"session_id":"s1"}]}"""
        val decoded = json.decodeFromString<PRsResponse>(payload)
        assertEquals(1, decoded.prs.size)
        assertEquals("axel", decoded.prs[0].elementType)
        assertEquals(45.2, decoded.prs[0].value)
    }

    @Test
    fun diagnosticsResponseDeserialize() {
        val payload = """{"user_id":"u1","findings":[{"severity":"warning","element":"axel","metric":"jump_height","message":"Below range","detail":"45cm vs 50cm"}]}"""
        val decoded = json.decodeFromString<DiagnosticsResponse>(payload)
        assertEquals("u1", decoded.userId)
        assertEquals(1, decoded.findings.size)
        assertEquals("warning", decoded.findings[0].severity)
    }

    // --- ProcessEvent parsedStatus edge cases ---

    @Test
    fun processEventStatusFailed() {
        val payload = """{"progress":1.0,"message":"GPU OOM","status":"failed"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(ProcessStatus.FAILED, decoded.parsedStatus)
    }

    @Test
    fun processEventStatusCancelled() {
        val payload = """{"progress":0.3,"message":"User cancelled","status":"cancelled"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(ProcessStatus.CANCELLED, decoded.parsedStatus)
    }

    @Test
    fun processEventStatusCompleted() {
        val payload = """{"progress":1.0,"message":"Done","status":"completed"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(ProcessStatus.COMPLETED, decoded.parsedStatus)
    }

    @Test
    fun processEventStatusUnknown() {
        val payload = """{"progress":0.0,"message":"","status":"pending"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(ProcessStatus.UNKNOWN, decoded.parsedStatus)
    }

    @Test
    fun processEventWithSessionId() {
        val payload = """{"progress":0.5,"message":"Processing","status":"running","session_id":"sess-42"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals("sess-42", decoded.sessionId)
    }

    @Test
    fun processEventDefaultValues() {
        val payload = """{}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(0f, decoded.progress)
        assertEquals("", decoded.message)
        assertEquals("running", decoded.status)
        assertEquals(null, decoded.sessionId)
    }

    // --- UserResponse default values ---

    @Test
    fun userResponseDefaultValues() {
        val payload = """{"id":"u1","email":"test@test.com"}"""
        val decoded = json.decodeFromString<UserResponse>(payload)
        assertEquals(null, decoded.displayName)
        assertEquals(null, decoded.avatarUrl)
        assertEquals(null, decoded.bio)
        assertEquals(null, decoded.heightCm)
        assertEquals(null, decoded.weightKg)
        assertEquals("ru", decoded.language)
        assertEquals("UTC", decoded.timezone)
        assertEquals("dark", decoded.theme)
        assertEquals(null, decoded.onboardingRole)
        assertEquals("deg_per_sec", decoded.angularUnit)
    }

    // --- MetricDefinition with optional fields ---

    @Test
    fun metricDefinitionMinimalFields() {
        val payload = """{"name":"jump_height","unit":"cm"}"""
        val decoded = json.decodeFromString<MetricDefinition>(payload)
        assertEquals("jump_height", decoded.name)
        assertEquals("cm", decoded.unit)
        assertEquals(null, decoded.labelRu)
        assertEquals(null, decoded.format)
        assertEquals(null, decoded.direction)
        assertEquals(null, decoded.elementTypes)
        assertEquals(null, decoded.idealRange)
    }

    // --- TrendDataPoint ---

    @Test
    fun trendDataPointRoundtrip() {
        val original = TrendDataPoint(sessionId = "s1", value = 42.5, isPr = true, date = "2026-05-01")
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<TrendDataPoint>(encoded)
        assertEquals(original, decoded)
    }

    // --- PersonalRecord ---

    @Test
    fun personalRecordRoundtrip() {
        val original = PersonalRecord(elementType = "axel", metricName = "jump_height", value = 45.2, sessionId = "s1")
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<PersonalRecord>(encoded)
        assertEquals(original, decoded)
    }

    // --- SummaryResponse ---

    @Test
    fun summaryResponseDeserialize() {
        val payload = """{"element":"axel","period":"last_30d","trend":"improving","findings":[],"metric_defs":{},"personal_records":[]}"""
        val decoded = json.decodeFromString<SummaryResponse>(payload)
        assertEquals("axel", decoded.element)
        assertEquals("last_30d", decoded.period)
        assertEquals("improving", decoded.trend)
    }

    // --- DiagnosticsFinding optional fields ---

    @Test
    fun diagnosticsFindingMinimalFields() {
        val payload = """{"severity":"info","message":"All metrics OK"}"""
        val decoded = json.decodeFromString<DiagnosticsFinding>(payload)
        assertEquals("info", decoded.severity)
        assertEquals("All metrics OK", decoded.message)
        assertEquals(null, decoded.element)
        assertEquals(null, decoded.metric)
        assertEquals(null, decoded.detail)
    }
}
