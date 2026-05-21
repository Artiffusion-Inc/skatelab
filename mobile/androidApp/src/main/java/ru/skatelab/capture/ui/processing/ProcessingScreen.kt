package ru.skatelab.capture.ui.processing

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import ru.skatelab.shared.state.ProcessingUiState

@Composable
fun ProcessingScreen(
    videoKey: String,
    sessionId: String? = null,
    onCompleted: (sessionId: String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: AndroidProcessingViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    // Kick off processing when screen appears
    LaunchedEffect(videoKey) {
        if (uiState is ProcessingUiState.Idle) {
            viewModel.startProcessing(videoKey, sessionId)
        }
    }

    // Navigate on completion
    LaunchedEffect(uiState) {
        if (uiState is ProcessingUiState.Completed) {
            val taskId = (uiState as ProcessingUiState.Completed).sessionId
            onCompleted(taskId)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        when (val state = uiState) {
            is ProcessingUiState.Idle -> {
                CircularProgressIndicator(modifier = Modifier.size(48.dp))
                Spacer(Modifier.height(16.dp))
                Text("Preparing...", style = MaterialTheme.typography.bodyLarge)
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
                // Handled by LaunchedEffect — show spinner while navigating
                CircularProgressIndicator(modifier = Modifier.size(48.dp))
                Spacer(Modifier.height(16.dp))
                Text("Done!", style = MaterialTheme.typography.bodyLarge)
            }

            is ProcessingUiState.Failed -> {
                val isNetworkError = state.message.lowercase().let { msg ->
                    msg.contains("network") || msg.contains("connection") ||
                        msg.contains("timeout") || msg.contains("socket") ||
                        msg.contains("unreachable") || msg.contains("resolve")
                }
                Icon(
                    imageVector = if (isNetworkError) Icons.Default.CloudOff else Icons.Default.ErrorOutline,
                    contentDescription = null,
                    modifier = Modifier.size(48.dp),
                    tint = MaterialTheme.colorScheme.error,
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    text = if (isNetworkError) "Нет подключения" else "Ошибка обработки",
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.error,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = if (isNetworkError) "Проверьте подключение к интернету и повторите." else state.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(24.dp))
                Button(
                    onClick = { viewModel.retry(videoKey, sessionId) },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Retry")
                }
                Spacer(Modifier.height(8.dp))
                OutlinedButton(
                    onClick = onBack,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Go back")
                }
            }
        }
    }
}