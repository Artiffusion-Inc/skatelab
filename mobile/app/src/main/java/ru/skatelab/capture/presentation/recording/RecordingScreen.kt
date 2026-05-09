package ru.skatelab.capture.presentation.recording

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun RecordingScreen(
    viewModel: RecordingViewModel,
    onStop: (String) -> Unit,
) {
    val isRecording by viewModel.isRecording.collectAsState()
    val error by viewModel.error.collectAsState()
    val sessionId by viewModel.sessionId.collectAsState()

    LaunchedEffect(sessionId) {
        sessionId?.let { onStop(it) }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Recording", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(24.dp))

        if (isRecording) {
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(16.dp))
            Text("Recording in progress...", style = MaterialTheme.typography.bodyLarge)
            Spacer(modifier = Modifier.height(24.dp))
            Button(
                onClick = { viewModel.stopRecording() },
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                ),
            ) { Text("Stop Recording") }
        }

        error?.let {
            Spacer(modifier = Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }
    }
}
