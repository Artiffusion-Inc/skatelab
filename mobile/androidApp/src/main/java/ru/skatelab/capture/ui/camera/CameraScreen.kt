package ru.skatelab.capture.ui.camera

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.compose.CameraXViewfinder
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.Bluetooth
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LocalLifecycleOwner
import java.io.File
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.ui.elements.ElementTypeBottomSheet

@Composable
fun CameraScreen(
    viewModel: CameraViewModel,
    onNavigateToImuCapture: () -> Unit,
    onNavigateToProcessing: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    val isRecording by viewModel.isRecording.collectAsState()
    val isPreviewReady by viewModel.isPreviewReady.collectAsState()
    val error by viewModel.error.collectAsState()
    val elapsedMs by viewModel.elapsedMs.collectAsState()
    val bleConnected by viewModel.bleConnected.collectAsState()
    val sensorInfo by viewModel.sensorInfo.collectAsState()
    val reconnectingSensor by viewModel.reconnectingSensor.collectAsState()
    val navigateToProcessing by viewModel.navigateToProcessing.collectAsState()
    val pendingElementType by viewModel.pendingElementType.collectAsState()
    val pendingUploadId by viewModel.pendingUploadId.collectAsState()

    var recordingElementType by remember { mutableStateOf("axel") }
    var showGalleryElementType by remember { mutableStateOf(false) }
    var galleryVideoPath by remember { mutableStateOf<String?>(null) }
    var galleryElementType by remember { mutableStateOf("axel") }

    // Navigate to ProcessingScreen after element type confirmed
    LaunchedEffect(navigateToProcessing) {
        navigateToProcessing?.let { uploadId ->
            onNavigateToProcessing(uploadId)
            viewModel.onNavigatedToProcessing()
        }
    }

    // Gallery video picker
    val videoPickerLauncher =
        rememberLauncherForActivityResult(
            contract = ActivityResultContracts.PickVisualMedia(),
        ) { uri: Uri? ->
            uri?.let {
                val destFile =
                    File(
                        context.getExternalFilesDir(android.os.Environment.DIRECTORY_MOVIES),
                        "gallery_${System.currentTimeMillis()}.mp4",
                    )
                try {
                    context.contentResolver.openInputStream(it)?.use { input ->
                        destFile.outputStream().use { output -> input.copyTo(output) }
                    }
                    galleryVideoPath = destFile.absolutePath
                    showGalleryElementType = true
                } catch (e: Exception) {
                    viewModel.setGalleryUploadError(context.getString(R.string.camera_gallery_copy_error))
                }
            }
        }

    var cameraBound by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.startBatteryPolling()
        viewModel.startBleMonitoring()
    }

    Box(modifier = modifier.fillMaxSize()) {
        // Camera preview
        CameraPreviewLayer(
            viewModel = viewModel,
            isRecording = isRecording,
            reconnectingSensor = reconnectingSensor,
            elapsedMs = elapsedMs,
            sensorInfo = sensorInfo,
            onCameraReady = {
                if (!cameraBound) {
                    cameraBound = true
                    viewModel.bindCamera(lifecycleOwner)
                }
            },
        )

        // Loading indicator
        if (!isPreviewReady) {
            Box(
                modifier =
                    Modifier
                        .fillMaxSize()
                        .background(Color.Black.copy(alpha = 0.6f)),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(48.dp),
                        color = Color.White,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        stringResource(R.string.camera_preparing),
                        color = Color.White,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }

        // Top bar: BLE indicator
        if (bleConnected) {
            Row(
                modifier =
                    Modifier
                        .align(Alignment.TopStart)
                        .padding(12.dp)
                        .background(Color.Black.copy(alpha = 0.6f), MaterialTheme.shapes.small)
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                        .testTag("cameraBleIndicator"),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(
                    Icons.Default.Bluetooth,
                    contentDescription = "BLE connected",
                    tint = Color.White,
                    modifier = Modifier.size(24.dp),
                )
                val parts = mutableListOf<String>()
                sensorInfo[SensorId.LEFT]?.let { parts.add("L:${it.batteryPercent}%") }
                sensorInfo[SensorId.RIGHT]?.let { parts.add("R:${it.batteryPercent}%") }
                if (parts.isNotEmpty()) {
                    Text(
                        parts.joinToString(" "),
                        color = Color.White,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }

        // IMU capture button (top right)
        FloatingActionButton(
            onClick = onNavigateToImuCapture,
            modifier =
                Modifier
                    .align(Alignment.TopEnd)
                    .padding(12.dp)
                    .testTag("cameraImuButton"),
            containerColor = MaterialTheme.colorScheme.secondaryContainer,
        ) {
            Icon(Icons.Default.Memory, contentDescription = "IMU capture")
        }

        // Bottom controls
        Column(
            modifier =
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(Color.Black.copy(alpha = 0.4f))
                    .padding(vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Gallery upload button
            if (!isRecording) {
                OutlinedButton(
                    onClick = {
                        videoPickerLauncher.launch(
                            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.VideoOnly),
                        )
                    },
                    modifier = Modifier.padding(bottom = 16.dp).testTag("cameraGalleryButton"),
                    colors =
                        androidx.compose.material3.ButtonDefaults.outlinedButtonColors(
                            contentColor = Color.White,
                        ),
                ) {
                    Icon(
                        Icons.Default.AttachFile,
                        contentDescription = stringResource(R.string.camera_gallery_upload),
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(stringResource(R.string.camera_gallery_upload))
                }
            }

            // Record button
            RecordButton(
                isRecording = isRecording,
                isPreviewReady = isPreviewReady,
                onToggle = { viewModel.toggleRecording(context) },
            )

            // Error message
            error?.let { message ->
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        // Element type bottom sheet after recording
        if (pendingElementType != null && pendingUploadId != null) {
            ElementTypeBottomSheet(
                selectedType = recordingElementType,
                onTypeSelected = { recordingElementType = it },
                onConfirm = {
                    viewModel.confirmElementType(pendingUploadId!!, recordingElementType)
                },
                onDismiss = {
                    viewModel.cancelElementTypeSelection()
                },
            )
        }

        // Element type bottom sheet for gallery upload
        if (showGalleryElementType) {
            ElementTypeBottomSheet(
                selectedType = galleryElementType,
                onTypeSelected = { galleryElementType = it },
                onConfirm = {
                    showGalleryElementType = false
                    galleryVideoPath?.let { path ->
                        viewModel.createGalleryUpload(path, galleryElementType)
                    }
                    galleryVideoPath = null
                },
                onDismiss = {
                    showGalleryElementType = false
                    galleryVideoPath = null
                },
            )
        }
    }
}

@Composable
private fun RecordButton(
    isRecording: Boolean,
    isPreviewReady: Boolean,
    onToggle: () -> Unit,
) {
    FloatingActionButton(
        onClick = onToggle,
        modifier = Modifier.size(72.dp).testTag("cameraRecordButton"),
        containerColor =
            if (isRecording) {
                MaterialTheme.colorScheme.error
            } else {
                Color.White
            },
        shape = CircleShape,
    ) {
        Box(
            modifier =
                Modifier
                    .size(if (isRecording) 24.dp else 56.dp)
                    .background(
                        color =
                            if (isRecording) {
                                Color.White
                            } else if (isPreviewReady) {
                                Color.Red
                            } else {
                                Color.Gray
                            },
                        shape = if (isRecording) MaterialTheme.shapes.extraSmall else CircleShape,
                    ),
        )
    }
}

@Composable
private fun CameraPreviewLayer(
    viewModel: CameraViewModel,
    isRecording: Boolean,
    reconnectingSensor: SensorId?,
    elapsedMs: Long,
    sensorInfo: Map<SensorId, ru.skatelab.capture.domain.model.SensorInfo?>,
    onCameraReady: () -> Unit,
) {
    val surfaceRequest by viewModel.surfaceRequest.collectAsState()

    Box(modifier = Modifier.fillMaxSize()) {
        surfaceRequest?.let { request ->
            CameraXViewfinder(
                surfaceRequest = request,
                modifier = Modifier.fillMaxSize(),
            )
        }

        LaunchedEffect(Unit) { onCameraReady() }

        // REC indicator with timer
        if (isRecording) {
            Box(
                modifier =
                    Modifier
                        .align(Alignment.TopCenter)
                        .padding(12.dp)
                        .background(Color.Red, MaterialTheme.shapes.small)
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                        .testTag("cameraRecIndicator"),
            ) {
                val totalSec = elapsedMs / 1000
                val min = (totalSec / 60).toInt()
                val sec = (totalSec % 60).toInt()
                Text(
                    "REC %02d:%02d".format(min, sec),
                    color = Color.White,
                    style = MaterialTheme.typography.labelLarge,
                )
            }

            // Reconnect warning
            if (reconnectingSensor != null) {
                Box(
                    modifier =
                        Modifier
                            .align(Alignment.TopStart)
                            .padding(12.dp)
                            .background(MaterialTheme.colorScheme.errorContainer, MaterialTheme.shapes.small)
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                ) {
                    Text(
                        stringResource(R.string.camera_reconnecting, reconnectingSensor?.name?.lowercase() ?: ""),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
        }
    }
}
