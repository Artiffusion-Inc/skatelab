package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class InviteRequest(
    @SerialName("to_user_email") val toUserEmail: String,
    @SerialName("connection_type") val connectionType: String,
)

@Serializable
data class ConnectionResponse(
    val id: String,
    @SerialName("from_user_id") val fromUserId: String,
    @SerialName("to_user_id") val toUserId: String,
    @SerialName("connection_type") val connectionType: String,
    val status: String,
    @SerialName("initiated_by") val initiatedBy: String?,
    @SerialName("created_at") val createdAt: String,
    @SerialName("ended_at") val endedAt: String?,
    @SerialName("from_user_name") val fromUserName: String? = null,
    @SerialName("to_user_name") val toUserName: String? = null,
)

@Serializable
data class ConnectionListResponse(
    val total: Int,
    val connections: List<ConnectionResponse>,
    val page: Int = 1,
    @SerialName("page_size") val pageSize: Int = 20,
    val pages: Int = 1,
)
