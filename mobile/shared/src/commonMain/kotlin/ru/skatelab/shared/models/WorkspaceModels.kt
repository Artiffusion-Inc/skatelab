package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class CreateWorkspaceRequest(
    val name: String,
    val slug: String,
    val description: String? = null,
)

@Serializable
data class WorkspaceResponse(
    val id: String,
    val name: String,
    val slug: String,
    val description: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class WorkspaceMemberResponse(
    val id: String,
    @SerialName("workspace_id") val workspaceId: String,
    @SerialName("user_id") val userId: String,
    val role: String,
    @SerialName("joined_at") val joinedAt: String,
    @SerialName("invited_by") val invitedBy: String? = null,
    @SerialName("user_name") val userName: String? = null,
    @SerialName("user_email") val userEmail: String? = null,
)

/** The invite and role-update routes intentionally share the backend request shape. */
@Serializable
data class InviteMemberRequest(
    val email: String,
    val role: String,
)

typealias Workspace = WorkspaceResponse
typealias WorkspaceMember = WorkspaceMemberResponse
