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
    @SerialName("pose_data") val poseData: PoseData? = null,
    @SerialName("frame_metrics") val frameMetrics: FrameMetrics? = null,
    val status: String,
    @SerialName("error_message") val errorMessage: String? = null,
    val phases: PhasesData? = null,
    val recommendations: List<String>? = null,
    @SerialName("overall_score") val overallScore: Float? = null,
    @SerialName("process_task_id") val processTaskId: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("processed_at") val processedAt: String? = null,
    val metrics: List<SessionMetricResponse> = emptyList(),
)