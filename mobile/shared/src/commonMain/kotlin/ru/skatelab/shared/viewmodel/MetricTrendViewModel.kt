package ru.skatelab.shared.viewmodel

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.shared.api.MetricsApi
import ru.skatelab.shared.state.TrendState
import ru.skatelab.shared.utils.toAppError

class MetricTrendViewModel(
    private val metricsApi: MetricsApi,
    private val scope: CoroutineScope,
) {
    private val _uiState = MutableStateFlow<TrendState>(TrendState.Loading)
    val uiState = _uiState.asStateFlow()

    fun load(metricName: String, elementType: String, period: String = "30d") {
        scope.launch {
            _uiState.value = TrendState.Loading
            try {
                val trend = metricsApi.getTrend(metricName, elementType, period)
                val registry = metricsApi.getRegistry()
                val metricDef = registry.metrics[metricName]
                    ?: throw NoSuchElementException("Unknown metric: $metricName")
                _uiState.value = TrendState.Loaded(trend, metricDef)
            } catch (e: Exception) {
                _uiState.value = TrendState.Error(e.toAppError())
            }
        }
    }

    fun changePeriod(metricName: String, elementType: String, period: String) {
        load(metricName, elementType, period)
    }
}