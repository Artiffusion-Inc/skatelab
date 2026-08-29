package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.SkillProgressResponse
import ru.skatelab.shared.models.UserLevelResponse

sealed interface GamificationUiState {
    data object Loading : GamificationUiState

    data class Loaded(
        val level: UserLevelResponse,
        val skills: List<SkillProgressResponse>,
    ) : GamificationUiState

    data class Error(val error: AppError) : GamificationUiState
}

typealias GamificationState = GamificationUiState
