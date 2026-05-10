package ru.skatelab.capture.presentation.recording

import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
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
    val lifecycleOwner = LocalLifecycleOwner.current
    val previewView = remember { PreviewView(context) }

    val isRecording by viewModel.isRecording.collectAsState()
    val isPreviewReady by viewModel.isPreviewReady.collectAsState()
    val error by viewModel.error.collectAsState()
    val sessionId by viewModel.sessionId.collectAsState()

    // Navigate on completion
    LaunchedEffect(sessionId) {
        sessionId?.let { onRecordingComplete(it) }
    }

    // Start/stop camera preview with lifecycle
    LaunchedEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.startPreview(previewView, lifecycleOwner)
            } else if (event == Lifecycle.Event.ON_PAUSE) {
                viewModel.stopPreview()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
    }

    DisposableEffect(Unit) {
        onDispose { viewModel.stopPreview() }
    }

    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Camera preview
        AndroidView(
            factory = { previewView },
            modifier = Modifier.weight(1f),
        )

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
                Spacer(modifier = Modifier.height(8.dp))
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
                Spacer(modifier = Modifier.height(4.dp))
                Text("Recording...", style = MaterialTheme.typography.bodySmall)
            }

            error?.let {
                Spacer(modifier = Modifier.height(8.dp))
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
