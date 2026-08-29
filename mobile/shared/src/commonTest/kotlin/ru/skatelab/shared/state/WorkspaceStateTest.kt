package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.WorkspaceMemberResponse
import ru.skatelab.shared.models.WorkspaceResponse
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class WorkspaceStateTest {
    @Test
    fun loaded_preservesWorkspacesSelectionAndMembers() {
        val workspace = WorkspaceResponse(
            id = "workspace-1",
            name = "Ice Academy",
            slug = "ice-academy",
            description = null,
            avatarUrl = null,
            isActive = true,
            createdAt = "2026-07-04T12:00:00Z",
            updatedAt = "2026-07-04T12:00:00Z",
        )
        val member = WorkspaceMemberResponse(
            id = "member-1",
            workspaceId = workspace.id,
            userId = "user-1",
            role = "owner",
            joinedAt = "2026-07-04T12:00:00Z",
            invitedBy = null,
        )

        val state: WorkspacesUiState = WorkspacesUiState.Loaded(
            workspaces = listOf(workspace),
            selectedWorkspace = workspace,
            members = listOf(member),
        )

        val loaded = assertIs<WorkspacesUiState.Loaded>(state)
        assertEquals(listOf(workspace), loaded.workspaces)
        assertEquals(workspace, loaded.selectedWorkspace)
        assertEquals(listOf(member), loaded.members)
    }

    @Test
    fun error_carriesTypedAppError() {
        val state: WorkspacesUiState = WorkspacesUiState.Error(AppError.Auth())

        val error = assertIs<WorkspacesUiState.Error>(state)
        assertIs<AppError.Auth>(error.error)
    }
}
