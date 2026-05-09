package ru.skatelab.capture.presentation.export

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@Composable
fun ExportScreen(
    viewModel: ExportViewModel,
    sessionId: String,
) {
    val isExporting by viewModel.isExporting.collectAsState()
    val exportPath by viewModel.exportPath.collectAsState()
    val error by viewModel.error.collectAsState()

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Export Session", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))
        Text("Session: $sessionId", style = MaterialTheme.typography.bodyMedium)
        Spacer(modifier = Modifier.height(24.dp))

        if (isExporting) {
            CircularProgressIndicator()
            Text("Exporting...")
        }

        exportPath?.let {
            Text("Exported to: $it", color = MaterialTheme.colorScheme.primary)
        }

        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
        }
    }
}
