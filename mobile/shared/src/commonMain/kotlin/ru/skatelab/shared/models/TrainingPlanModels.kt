package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TrainingPlanItem(
    val id: String,
    val priority: Int,
    @SerialName("label_ru") val labelRu: String,
    @SerialName("description_ru") val descriptionRu: String,
    val completed: Boolean,
)

@Serializable
data class TrainingPlanResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("session_id") val sessionId: String?,
    val items: List<TrainingPlanItem>,
    @SerialName("generated_at") val generatedAt: String,
    val completed: Boolean,
    @SerialName("focus_subscore") val focusSubscore: String?,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class GenerateTrainingPlanRequest(
    @SerialName("session_id") val sessionId: String,
)
