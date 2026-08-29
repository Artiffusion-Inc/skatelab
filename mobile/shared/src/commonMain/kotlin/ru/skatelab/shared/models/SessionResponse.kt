package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class SessionResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("element_type") val elementType: String? = null,
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
    @SerialName("workspace_id") val workspaceId: String? = null,
    @SerialName("video_key") val videoKey: String? = null,
    @SerialName("processed_video_key") val processedVideoKey: String? = null,
    @SerialName("poses_url") val posesUrl: String? = null,
    @SerialName("csv_url") val csvUrl: String? = null,
    @SerialName("imu_left_key") val imuLeftKey: String? = null,
    @SerialName("imu_right_key") val imuRightKey: String? = null,
    @SerialName("manifest_key") val manifestKey: String? = null,
    @SerialName("isu_code") val isuCode: String? = null,
    val timeline: SessionTimeline? = null,
    @SerialName("segmentation_status") val segmentationStatus: String = "pending",
    @SerialName("goe_grade") val goeGrade: GoeGrade? = null,
)

@Serializable
data class SessionTimeline(
    val segments: List<SessionElementSegment> = emptyList(),
    @SerialName("segmentation_confidence") val segmentationConfidence: Float? = null,
    @SerialName("segmentation_status") val segmentationStatus: String = "pending",
)

@Serializable
data class SessionElementSegment(
    val id: String,
    @SerialName("element_type") val elementType: String,
    @SerialName("element_name") val elementName: String? = null,
    @SerialName("start_frame") val startFrame: Int,
    @SerialName("end_frame") val endFrame: Int,
    val confidence: Float,
    @SerialName("phases_json") val phasesJson: Map<String, JsonElement>? = null,
)

@Serializable
data class GoeGrade(
    val grade: Int,
    @SerialName("base_value") val baseValue: Float,
    @SerialName("estimated_score") val estimatedScore: Float,
    val modifier: String,
    val positives: List<String>,
    val negatives: List<String>,
    val confidence: Float,
    val deductions: List<Map<String, JsonElement>>,
)