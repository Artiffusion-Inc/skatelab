package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UserLevelResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    val level: Int,
    @SerialName("total_xp") val totalXp: Int,
    @SerialName("xp_to_next") val xpToNext: Int,
    val title: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class SkillProgressResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("skill_id") val skillId: String,
    val category: String,
    val tier: String,
    val unlocked: Boolean,
    @SerialName("unlocked_at") val unlockedAt: String? = null,
    @SerialName("consecutive_sessions") val consecutiveSessions: Int,
    @SerialName("best_score") val bestScore: Double,
    @SerialName("xp_reward") val xpReward: Int,
)

typealias UserLevel = UserLevelResponse
typealias SkillProgress = SkillProgressResponse
