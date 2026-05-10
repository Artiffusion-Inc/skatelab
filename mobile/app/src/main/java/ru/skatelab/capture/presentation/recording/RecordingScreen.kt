package ru.skatelab.capture.presentation.recording

import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import ru.skatelab.capture.R
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

    // Track whether the PreviewView surface has been provided to the ViewModel,
    // so we only call prepareCamera once after the surface is available.
    var surfaceProvided by remember { mutableStateOf(false) }

    // Navigate on completion
    LaunchedEffect(sessionId) {
        sessionId?.let { onRecordingComplete(it) }
    }

    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Camera preview area
        Box(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentAlignment = Alignment.Center,
        ) {
            CameraPreview(
                viewModel = viewModel,
                isRecording = isRecording,
                onSurfaceReady = {
                    if (!surfaceProvided) {
                        surfaceProvided = true
                        viewModel.prepareCamera(outputDir)
                    }
                },
            )

            // Loading overlay while camera is preparing (before preview is ready)
            if (!isPreviewReady) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(modifier = Modifier.size(48.dp))
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        stringResource(R.string.recording_preparing),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
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
                    Text(stringResource(R.string.recording_start))
                }
            } else {
                Button(
                    onClick = { viewModel.stopRecording(context) },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.recording_stop))
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

@Composable
private fun CameraPreview(
    viewModel: RecordingViewModel,
    isRecording: Boolean,
    onSurfaceReady: () -> Unit,
) {
    Box(modifier = Modifier.fillMaxSize()) {
        AndroidView(
            factory = { context ->
                PreviewView(context).apply {
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    // Provide the surface provider to the ViewModel once the PreviewView
                    // is created. The PreviewView's surfaceProvider manages the surface
                    // lifecycle (creation, destruction, resize) for CameraX.
                    // Also extract the Surface for Camera2-based recorder fallback.
                    post {
                        // CameraX path: pass PreviewView's surfaceProvider
                        viewModel.setPreviewSurfaceProvider(surfaceProvider)
                        // Camera2 path: extract Surface from the internal SurfaceView
                        val surfaceView = getChildAt(0) as? android.view.SurfaceView
                        surfaceView?.holder?.surface?.let { surface ->
                            viewModel.setPreviewSurface(surface)
                        }
                        onSurfaceReady()
                    }
                }
            },
            modifier = Modifier.fillMaxSize(),
        )

        // REC indicator overlay
        if (isRecording) {
            Box(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(12.dp)
                    .background(Color.Red, MaterialTheme.shapes.small)
                    .padding(horizontal = 8.dp, vertical = 4.dp),
            ) {
                Text("REC", color = Color.White, style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}
