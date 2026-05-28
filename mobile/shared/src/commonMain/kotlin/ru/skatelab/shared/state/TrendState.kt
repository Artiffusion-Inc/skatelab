package ru.skatelab.shared.state

import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.models.MetricDefinition
import ru.skatelab.shared.models.TrendResponse

sealed interface TrendState {
    data object Loading : TrendState
    data class Loaded(
        val trend: TrendResponse,
        val metricDef: MetricDefinition,
    ) : TrendState
    data class Error(val error: AppError) : TrendState
}