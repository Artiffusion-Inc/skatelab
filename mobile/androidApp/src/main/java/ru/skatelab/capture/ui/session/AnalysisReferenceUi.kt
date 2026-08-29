package ru.skatelab.capture.ui.session

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.PhotoLibrary
import androidx.compose.material.icons.outlined.SportsScore
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.ui.elements.elementLabel
import ru.skatelab.shared.models.elementTypes
import ru.skatelab.shared.state.SessionsUiState

@Composable
internal fun SessionListContent(
    loaded: SessionsUiState.Loaded,
    selectedElementType: String?,
    onSessionClick: (String) -> Unit,
    onStartAnalysis: () -> Unit,
    onOpenFilters: () -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val listState = rememberLazyListState()
    val sessions = loaded.sessions

    LaunchedEffect(listState, sessions.size, loaded.hasMore, loaded.isLoadingMore) {
        androidx.compose.runtime.snapshotFlow {
            listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index
        }.collect { lastVisible ->
            val totalItems = listState.layoutInfo.totalItemsCount
            if (
                loaded.hasMore &&
                !loaded.isLoadingMore &&
                lastVisible != null &&
                totalItems > 0 &&
                lastVisible >= totalItems - 2
            ) {
                onLoadMore()
            }
        }
    }

    LazyColumn(
        state = listState,
        modifier = modifier.fillMaxSize().testTag("sessionListContent"),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 24.dp),
    ) {
        item {
            AnalysisHero(onStartAnalysis = onStartAnalysis)
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.analysis_recent),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                OutlinedButton(
                    onClick = onOpenFilters,
                    modifier = Modifier.testTag("analysisFilterButton"),
                ) {
                    Icon(
                        imageVector = Icons.Outlined.FilterList,
                        contentDescription = null,
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(stringResource(R.string.analysis_filters))
                }
            }
        }
        item {
            AnalysisFilterChips(
                selectedElementType = selectedElementType,
                onSelect = onOpenFilters,
            )
        }

        if (sessions.isEmpty()) {
            item {
                AnalysisEmptyState(onStartAnalysis = onStartAnalysis)
            }
        } else {
            items(sessions, key = { it.id }) { session ->
                SessionCard(
                    session = session,
                    onClick = { onSessionClick(session.id) },
                )
            }
            if (loaded.isLoadingMore) {
                item {
                    androidx.compose.foundation.layout.Box(
                        modifier = Modifier.fillMaxWidth().padding(16.dp),
                        contentAlignment = Alignment.Center,
                    ) {
                        androidx.compose.material3.CircularProgressIndicator()
                    }
                }
            }
        }
    }
}

@Composable
private fun AnalysisHero(onStartAnalysis: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().testTag("analysisNewCard"),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(24.dp),
        colors =
            CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.secondaryContainer,
            ),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text(
                text = stringResource(R.string.analysis_new_title),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = stringResource(R.string.analysis_new_body),
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(modifier = Modifier.height(16.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(
                    onClick = onStartAnalysis,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Outlined.Videocam, contentDescription = null)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(stringResource(R.string.analysis_record_video))
                }
                Button(
                    onClick = onStartAnalysis,
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Outlined.PhotoLibrary, contentDescription = null)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(stringResource(R.string.analysis_choose_video))
                }
            }
        }
    }
}

@Composable
private fun AnalysisFilterChips(
    selectedElementType: String?,
    onSelect: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FilterChip(
            selected = selectedElementType == null,
            onClick = onSelect,
            label = { Text(stringResource(R.string.analysis_filter_all)) },
        )
        FilterChip(
            selected = false,
            onClick = onSelect,
            label = { Text(stringResource(R.string.analysis_filter_jumps)) },
        )
        FilterChip(
            selected = false,
            onClick = onSelect,
            label = { Text(stringResource(R.string.analysis_filter_spins)) },
        )
        FilterChip(
            selected = false,
            onClick = onSelect,
            label = { Text(stringResource(R.string.analysis_filter_steps)) },
        )
        FilterChip(
            selected = false,
            onClick = onSelect,
            label = { Text(stringResource(R.string.analysis_filter_combinations)) },
        )
    }
}

@Composable
private fun AnalysisEmptyState(onStartAnalysis: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = 36.dp).testTag("analysisEmptyState"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            imageVector = Icons.Outlined.SportsScore,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            text = stringResource(R.string.empty_sessions_title),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.empty_sessions_body),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(16.dp))
        Button(onClick = onStartAnalysis) {
            Text(stringResource(R.string.analysis_start))
        }
    }
}

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
internal fun SessionFilterSheet(
    selectedElementType: String?,
    onApply: (String?) -> Unit,
    onDismiss: () -> Unit,
) {
    var pendingElementType by remember(selectedElementType) { mutableStateOf(selectedElementType) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = Modifier.testTag("sessionFilterSheet"),
    ) {
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.analysis_filter_title),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                IconButton(
                    onClick = onDismiss,
                    modifier = Modifier.testTag("closeSessionFilters"),
                ) {
                    Text(
                        text = "×",
                        style = MaterialTheme.typography.headlineMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Text(
                text = stringResource(R.string.analysis_filter_element_type),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FilterChip(
                    selected = pendingElementType == null,
                    onClick = { pendingElementType = null },
                    label = { Text(stringResource(R.string.analysis_filter_all)) },
                )
                elementTypes.forEach { key ->
                    FilterChip(
                        selected = pendingElementType == key,
                        onClick = { pendingElementType = key },
                        label = { Text(elementLabel(key)) },
                    )
                }
            }

            Text(
                text = stringResource(R.string.analysis_filter_attempts),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            FilterChip(
                selected = false,
                onClick = {},
                enabled = false,
                label = { Text(stringResource(R.string.analysis_filter_all)) },
            )

            Text(
                text = stringResource(R.string.analysis_filter_status),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = false,
                    onClick = {},
                    enabled = false,
                    label = { Text(stringResource(R.string.analysis_status_completed)) },
                )
                FilterChip(
                    selected = false,
                    onClick = {},
                    enabled = false,
                    label = { Text(stringResource(R.string.analysis_status_processing)) },
                )
                FilterChip(
                    selected = false,
                    onClick = {},
                    enabled = false,
                    label = { Text(stringResource(R.string.analysis_status_draft)) },
                )
            }

            Text(
                text = stringResource(R.string.analysis_filter_period),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = true,
                    onClick = {},
                    enabled = false,
                    label = { Text(stringResource(R.string.analysis_period_week)) },
                )
                FilterChip(
                    selected = false,
                    onClick = {},
                    enabled = false,
                    label = { Text(stringResource(R.string.analysis_period_month)) },
                )
                FilterChip(
                    selected = false,
                    onClick = {},
                    enabled = false,
                    label = { Text(stringResource(R.string.analysis_period_season)) },
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                TextButton(
                    onClick = {
                        pendingElementType = null
                        onApply(null)
                    },
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.analysis_filter_reset))
                }
                Button(
                    onClick = { onApply(pendingElementType) },
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.analysis_filter_apply))
                }
            }
        }
    }
}
