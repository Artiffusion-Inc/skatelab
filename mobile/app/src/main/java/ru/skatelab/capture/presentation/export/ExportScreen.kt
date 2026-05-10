package ru.skatelab.capture.presentation.export

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

@Composable
fun ExportScreen(
    viewModel: ExportViewModel,
    sessionId: String,
) {
    val context = LocalContext.current
    val isExporting by viewModel.isExporting.collectAsState()
    val exportPath by viewModel.exportPath.collectAsState()
    val error by viewModel.error.collectAsState()

    // Auto-trigger export on first composition
    LaunchedEffect(sessionId) {
        if (exportPath == null && !isExporting && error == null) {
            val downloadsDir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
            val outputDir = java.io.File(downloadsDir, "skatelab_exports")
            outputDir.mkdirs()
            viewModel.export(sessionId, outputDir)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Export Session", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(8.dp))
        Text("Session: $sessionId", style = MaterialTheme.typography.bodyMedium)
        Spacer(modifier = Modifier.height(24.dp))

        if (isExporting) {
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(8.dp))
            Text("Exporting...")
        }

        exportPath?.let {
            Text("Export complete!", color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(8.dp))
            Text(it, style = MaterialTheme.typography.bodySmall)
        }

        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
        }
    }
}
