package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.api.TrainingPlansApi
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.GenerateTrainingPlanRequest
import ru.skatelab.shared.models.TrainingPlanResponse
import ru.skatelab.shared.utils.toAppError

sealed interface TrainingPlansState {
    data object Loading : TrainingPlansState
    data class Loaded(val plan: TrainingPlanResponse) : TrainingPlansState
    data class Error(val error: AppError) : TrainingPlansState
}

typealias TrainingPlanUiState = TrainingPlansState
typealias TrainingPlanState = TrainingPlansState

typealias TrainingPlansUiState = TrainingPlansState

class TrainingPlansViewModel(private val trainingPlansApi: TrainingPlansApi) {
    private val _uiState = MutableStateFlow<TrainingPlansState>(TrainingPlansState.Loading)
    val uiState: StateFlow<TrainingPlansState> = _uiState.asStateFlow()

    suspend fun loadPlan(planId: String) {
        _uiState.value = TrainingPlansState.Loading
        try {
            _uiState.value = TrainingPlansState.Loaded(trainingPlansApi.get(planId))
        } catch (e: Exception) {
            _uiState.value = TrainingPlansState.Error(e.toAppError())
        }
    }

    suspend fun generatePlan(sessionId: String) {
        _uiState.value = TrainingPlansState.Loading
        try {
            _uiState.value = TrainingPlansState.Loaded(
                trainingPlansApi.generate(GenerateTrainingPlanRequest(sessionId)),
            )
        } catch (e: Exception) {
            _uiState.value = TrainingPlansState.Error(e.toAppError())
        }
    }
}
