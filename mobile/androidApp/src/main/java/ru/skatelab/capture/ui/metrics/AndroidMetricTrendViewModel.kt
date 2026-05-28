package ru.skatelab.capture.ui.metrics

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.viewmodel.MetricTrendViewModel

@HiltViewModel
class AndroidMetricTrendViewModel
@Inject
constructor(
    client: SkateLabClient,
) : ViewModel() {
    val shared =
        MetricTrendViewModel(
            metricsApi = client.metrics,
            scope = viewModelScope,
        )
}