package ru.skatelab.capture.presentation.export

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import java.io.File

@Composable
fun ExportScreen(
    viewModel: ExportViewModel,
    sessionId: String,
    onExportComplete: () -> Unit = {},
) {
    val context = LocalContext.current
    val isExporting by viewModel.isExporting.collectAsState()
    val exportPath by viewModel.exportPath.collectAsState()
    val shareUri by viewModel.shareUri.collectAsState()
    val error by viewModel.error.collectAsState()

    // Auto-trigger export on first composition
    LaunchedEffect(sessionId) {
        if (exportPath == null && !isExporting && error == null) {
            val outputDir = File(context.getExternalFilesDir(android.os.Environment.DIRECTORY_DOWNLOADS), "skatelab_exports")
            outputDir.mkdirs()
            viewModel.export(sessionId, outputDir)
        }
    }

    // Launch share sheet when shareUri is set
    LaunchedEffect(shareUri) {
        shareUri?.let { uri ->
            val shareIntent = Intent(Intent.ACTION_SEND).apply {
                type = "application/zip"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            context.startActivity(
                Intent.createChooser(shareIntent, context.getString(R.string.export_share_title))
            )
            viewModel.onShareComplete()
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            stringResource(R.string.export_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            stringResource(R.string.export_session, sessionId),
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(modifier = Modifier.height(24.dp))

        if (isExporting) {
            CircularProgressIndicator()
            Spacer(modifier = Modifier.height(8.dp))
            Text(stringResource(R.string.exporting))
        }

        exportPath?.let { path ->
            Text(
                stringResource(R.string.export_done),
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(path, style = MaterialTheme.typography.bodySmall)
            Spacer(modifier = Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Button(
                    onClick = { viewModel.onShareClicked() },
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.export_share))
                }

                Button(
                    onClick = onExportComplete,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(stringResource(R.string.session_list_title))
                }
            }
        }

        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
        }
    }
}
