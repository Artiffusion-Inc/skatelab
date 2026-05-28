package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.MetricDefinition
import ru.skatelab.shared.models.SessionResponse

sealed interface SessionDetailState {
    data object Loading : SessionDetailState
    data class Loaded(
        val session: SessionResponse,
        val metricDefs: Map<String, MetricDefinition>,
        val showSkeleton: Boolean = true,
    ) : SessionDetailState
    data class Error(val error: AppError) : SessionDetailState
}