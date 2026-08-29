package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import ru.skatelab.shared.models.CreateWorkspaceRequest
import ru.skatelab.shared.models.InviteMemberRequest
import ru.skatelab.shared.models.WorkspaceMemberResponse
import ru.skatelab.shared.models.WorkspaceResponse
import ru.skatelab.shared.utils.expectSuccess

class WorkspacesApi(private val client: HttpClient) {
    suspend fun create(request: CreateWorkspaceRequest): WorkspaceResponse =
        client.post("workspaces") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun create(
        name: String,
        slug: String,
        description: String? = null,
    ): WorkspaceResponse = create(CreateWorkspaceRequest(name, slug, description))

    suspend fun list(): List<WorkspaceResponse> =
        client.get("workspaces").expectSuccess().body()

    suspend fun get(workspaceId: String): WorkspaceResponse =
        client.get("workspaces/$workspaceId").expectSuccess().body()

    suspend fun invite(
        workspaceId: String,
        request: InviteMemberRequest,
    ): WorkspaceMemberResponse =
        client.post("workspaces/$workspaceId/invite") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun invite(
        workspaceId: String,
        email: String,
        role: String,
    ): WorkspaceMemberResponse = invite(workspaceId, InviteMemberRequest(email, role))

    suspend fun listMembers(workspaceId: String): List<WorkspaceMemberResponse> =
        client.get("workspaces/$workspaceId/members").expectSuccess().body()

    suspend fun removeMember(workspaceId: String, userId: String) {
        client.delete("workspaces/$workspaceId/members/$userId").expectSuccess()
    }

    suspend fun updateRole(
        workspaceId: String,
        userId: String,
        request: InviteMemberRequest,
    ): WorkspaceMemberResponse =
        client.patch("workspaces/$workspaceId/members/$userId/role") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun updateRole(
        workspaceId: String,
        userId: String,
        email: String,
        role: String,
    ): WorkspaceMemberResponse =
        updateRole(workspaceId, userId, InviteMemberRequest(email, role))
}
