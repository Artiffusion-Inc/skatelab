package ru.skatelab.capture.presentation.recording

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId
import java.io.File

@Composable
fun RecordingScreen(
    viewModel: RecordingViewModel,
    outputDir: File,
    calibration: Map<SensorId, CalibrationData>,
    onRecordingComplete: (String) -> Unit,
) {
    val context = LocalContext.current

    val isRecording by viewModel.isRecording.collectAsState()
    val isPreviewReady by viewModel.isPreviewReady.collectAsState()
    val error by viewModel.error.collectAsState()
    val sessionId by viewModel.sessionId.collectAsState()

    // Navigate on completion
    LaunchedEffect(sessionId) {
        sessionId?.let { onRecordingComplete(it) }
    }

    // Prepare camera on first composition
    LaunchedEffect(Unit) {
        viewModel.prepareCamera(outputDir)
    }

    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Camera status indicator (Camera2 handles preview surface internally)
        Box(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentAlignment = Alignment.Center,
        ) {
            if (isRecording) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(modifier = Modifier.size(48.dp))
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Recording...", style = MaterialTheme.typography.titleMedium)
                }
            } else if (isPreviewReady) {
                Text(
                    "Camera ready",
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
            } else {
                CircularProgressIndicator(modifier = Modifier.size(48.dp))
                Spacer(modifier = Modifier.height(8.dp))
                Text("Preparing camera...", style = MaterialTheme.typography.bodyMedium)
            }
        }

        // Controls
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (!isRecording) {
                Button(
                    onClick = {
                        viewModel.startRecording(outputDir, calibration, context)
                    },
                    enabled = isPreviewReady,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Start Recording")
                }
            } else {
                Button(
                    onClick = { viewModel.stopRecording(context) },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("Stop Recording")
                }
            }

            error?.let {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    it,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}
