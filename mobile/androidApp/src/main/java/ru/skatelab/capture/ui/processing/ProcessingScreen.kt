package ru.skatelab.capture.ui.processing

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import ru.skatelab.capture.R
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.models.AppError
import ru.skatelab.shared.state.ProcessingUiState

@Composable
fun ProcessingScreen(
    uploadId: String?,
    sessionId: String?,
    onCompleted: (sessionId: String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: AndroidProcessingViewModel = hiltViewModel(),
) {
    val uploadPhase by viewModel.uploadPhase.collectAsState()
    val processingState by viewModel.processingState.collectAsState()

    // Phase 1: Observe upload status from Room
    LaunchedEffect(uploadId) {
        if (uploadId != null) {
            viewModel.observeUpload(uploadId)
        }
    }

    // Phase 2: When ready, kick off SSE processing
    LaunchedEffect(uploadPhase) {
        if (uploadPhase is UploadPhase.ReadyForProcessing) {
            val ready = uploadPhase as UploadPhase.ReadyForProcessing
            if (processingState is ProcessingUiState.Idle) {
                viewModel.startSseProcessing(ready.videoKey, ready.sessionId)
            }
        }
    }

    // Direct SSE entry (sessionId only, no uploadId)
    LaunchedEffect(sessionId) {
        if (uploadId == null && sessionId != null && processingState is ProcessingUiState.Idle) {
            viewModel.startSseProcessing("", sessionId)
        }
    }

    // Navigate on SSE completion
    LaunchedEffect(processingState) {
        if (processingState is ProcessingUiState.Completed) {
            val taskId = (processingState as ProcessingUiState.Completed).sessionId
            onCompleted(taskId)
        }
    }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        when {
            // Upload phase
            uploadPhase is UploadPhase.UploadStatus -> {
                val entity = (uploadPhase as UploadPhase.UploadStatus).entity
                UploadStatusContent(entity = entity)
            }
            // Upload failed
            uploadPhase is UploadPhase.UploadFailed -> {
                UploadFailedContent(
                    onRetry = { uploadId?.let { viewModel.observeUpload(it) } },
                    onBack = onBack,
                )
            }
            // SSE processing phase
            else ->
                ProcessingContent(
                    state = processingState,
                    onRetry = { viewModel.retry("", sessionId) },
                    onBack = onBack,
                )
        }
    }
}

@Composable
private fun UploadStatusContent(entity: PendingUploadEntity) {
    val context = LocalContext.current
    val statusText =
        when (entity.status) {
            "READY" -> context.getString(R.string.upload_status_ready)
            "UPLOADING" -> context.getString(R.string.upload_status_uploading)
            else -> entity.status
        }
    Box(
        modifier =
            Modifier.semantics(mergeDescendants = true) {
                contentDescription = statusText
                role = Role.ValuePicker
            },
    ) {
        CircularProgressIndicator(modifier = Modifier.size(48.dp))
    }
    Spacer(Modifier.height(16.dp))
    Text(statusText, style = MaterialTheme.typography.bodyLarge)
}

@Composable
private fun UploadFailedContent(
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    Icon(
        imageVector = Icons.Default.CloudOff,
        contentDescription = stringResource(R.string.cd_error_icon),
        modifier = Modifier.size(48.dp),
        tint = MaterialTheme.colorScheme.error,
    )
    Spacer(Modifier.height(12.dp))
    Text(
        text = stringResource(R.string.processing_error),
        style = MaterialTheme.typography.headlineSmall,
        color = MaterialTheme.colorScheme.error,
        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
    )
    Spacer(Modifier.height(24.dp))
    Button(
        onClick = onRetry,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(stringResource(R.string.processing_retry))
    }
    Spacer(Modifier.height(8.dp))
    OutlinedButton(
        onClick = onBack,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(stringResource(R.string.processing_go_back))
    }
}

@Composable
private fun ProcessingContent(
    state: ProcessingUiState,
    onRetry: () -> Unit,
    onBack: () -> Unit,
) {
    when (state) {
        is ProcessingUiState.Idle -> {
            val context = LocalContext.current
            Box(
                modifier =
                    Modifier.semantics(mergeDescendants = true) {
                        contentDescription = context.getString(R.string.cd_loading)
                        role = Role.ValuePicker
                    },
            ) {
                CircularProgressIndicator(modifier = Modifier.size(48.dp))
            }
            Spacer(Modifier.height(16.dp))
            Text(stringResource(R.string.processing_preparing), style = MaterialTheme.typography.bodyLarge)
        }

        is ProcessingUiState.Progress -> {
            LinearProgressIndicator(
                progress = { state.percent },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(16.dp))
            Text(
                text = state.message.ifBlank { "Processing..." },
                style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "${(state.percent * 100).toInt()}%",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        is ProcessingUiState.Completed -> {
            val context = LocalContext.current
            Box(
                modifier =
                    Modifier.semantics(mergeDescendants = true) {
                        contentDescription = context.getString(R.string.cd_loading)
                        role = Role.ValuePicker
                    },
            ) {
                CircularProgressIndicator(modifier = Modifier.size(48.dp))
            }
            Spacer(Modifier.height(16.dp))
            Text(stringResource(R.string.processing_done), style = MaterialTheme.typography.bodyLarge)
        }

        is ProcessingUiState.Failed -> {
            val isNetworkError = state.error is AppError.Network || state.error is AppError.Timeout
            Icon(
                imageVector = if (isNetworkError) Icons.Default.CloudOff else Icons.Default.ErrorOutline,
                contentDescription = stringResource(R.string.cd_error_icon),
                modifier = Modifier.size(48.dp),
                tint = MaterialTheme.colorScheme.error,
            )
            Spacer(Modifier.height(12.dp))
            Text(
                text = if (isNetworkError) stringResource(R.string.processing_no_connection) else stringResource(R.string.processing_error),
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = if (isNetworkError) stringResource(R.string.processing_check_network) else stringResource(R.string.processing_error),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(24.dp))
            Button(
                onClick = onRetry,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.processing_retry))
            }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(
                onClick = onBack,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.processing_go_back))
            }
        }
    }
}
