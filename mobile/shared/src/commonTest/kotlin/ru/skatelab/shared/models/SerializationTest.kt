package ru.skatelab.shared.models

import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import ru.skatelab.shared.api.PresignResponse
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
            heightCm = 165f,
            weightKg = 52f,
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
}
