package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.WorkspaceMemberResponse
import ru.skatelab.shared.models.WorkspaceResponse

sealed interface WorkspacesUiState {
    data object Loading : WorkspacesUiState

    data class Loaded(
        val workspaces: List<WorkspaceResponse>,
        val selectedWorkspace: WorkspaceResponse? = null,
        val members: List<WorkspaceMemberResponse> = emptyList(),
    ) : WorkspacesUiState

    data class Error(val error: AppError) : WorkspacesUiState
}

typealias WorkspacesState = WorkspacesUiState
typealias WorkspaceState = WorkspacesUiState
