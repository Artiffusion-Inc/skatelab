package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("element_type") val elementType: String,
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("processed_video_url") val processedVideoUrl: String? = null,
    val status: String,
    @SerialName("overall_score") val overallScore: Float? = null,
    val recommendations: List<String>? = null,
    val metrics: List<SessionMetricResponse> = emptyList(),
    @SerialName("created_at") val createdAt: String,
)
