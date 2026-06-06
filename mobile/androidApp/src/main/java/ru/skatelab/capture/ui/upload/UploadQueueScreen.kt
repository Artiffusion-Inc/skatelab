package ru.skatelab.capture.ui.upload

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.models.elementLabelRu

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UploadQueueScreen(
    viewModel: UploadQueueViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val uploads by viewModel.uploads.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.upload_queue_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = stringResource(R.string.nav_back),
                        )
                    }
                },
            )
        },
        modifier = modifier,
    ) { padding ->
        if (uploads.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.CloudDone,
                        contentDescription = null,
                        modifier = Modifier.size(48.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        stringResource(R.string.upload_queue_empty),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding).testTag("uploadQueueList"),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(16.dp),
            ) {
                items(uploads, key = { it.id }) { entity ->
                    UploadCard(
                        entity = entity,
                        onRetry = { viewModel.retry(entity.id) },
                        onCancel = { viewModel.cancel(entity.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun UploadCard(
    entity: PendingUploadEntity,
    onRetry: () -> Unit,
    onCancel: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = entity.videoPath.substringAfterLast("/"),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                    )
                    Text(
                        text = (entity.elementType ?: "axel").elementLabelRu(),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                StatusChip(status = entity.status)
            }

            if (entity.status == "FAILED") {
                Spacer(modifier = Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = onRetry) {
                        Text(stringResource(R.string.upload_queue_retry))
                    }
                    OutlinedButton(onClick = onCancel) {
                        Text(stringResource(R.string.upload_queue_cancel))
                    }
                }
            }

            if (entity.status == "UPLOADING" || entity.status == "PROCESSING") {
                Spacer(modifier = Modifier.height(8.dp))
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun StatusChip(status: String) {
    val (text, color) =
        when (status) {
            "READY" -> stringResource(R.string.upload_status_ready) to MaterialTheme.colorScheme.onSurfaceVariant
            "UPLOADING" -> stringResource(R.string.upload_status_uploading) to MaterialTheme.colorScheme.primary
            "PROCESSING" -> stringResource(R.string.upload_status_processing) to MaterialTheme.colorScheme.primary
            "COMPLETED" -> stringResource(R.string.upload_status_completed) to Color(0xFF4CAF50)
            "FAILED" -> stringResource(R.string.upload_status_failed) to MaterialTheme.colorScheme.error
            else -> status to MaterialTheme.colorScheme.onSurfaceVariant
        }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (status == "UPLOADING" || status == "PROCESSING") {
            CircularProgressIndicator(modifier = Modifier.size(12.dp), strokeWidth = 2.dp)
        }
        Text(text = text, style = MaterialTheme.typography.labelMedium, color = color)
    }
}
