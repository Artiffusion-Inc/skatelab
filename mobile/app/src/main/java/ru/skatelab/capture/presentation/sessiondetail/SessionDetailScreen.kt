package ru.skatelab.capture.presentation.sessiondetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import ru.skatelab.capture.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SessionDetailScreen(
    viewModel: SessionDetailViewModel,
    sessionId: String,
    onBack: () -> Unit,
    onExport: (String) -> Unit,
) {
    val session by viewModel.session.collectAsState()

    LaunchedEffect(sessionId) {
        viewModel.loadSession(sessionId)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.session_detail_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            session?.let { s ->
                val dateFormat =
                    SimpleDateFormat(
                        stringResource(R.string.session_date_format),
                        Locale.getDefault(),
                    )
                Text(
                    dateFormat.format(Date(s.createdAt)),
                    style = MaterialTheme.typography.headlineMedium,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    stringResource(R.string.session_duration, s.durationMs / 1000),
                    style = MaterialTheme.typography.bodyLarge,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    if (s.isComplete) {
                        stringResource(R.string.session_complete)
                    } else {
                        stringResource(R.string.session_incomplete)
                    },
                    style = MaterialTheme.typography.labelLarge,
                    color =
                        if (s.isComplete) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.error
                        },
                )
                Spacer(modifier = Modifier.height(24.dp))
                androidx.compose.material3.Button(onClick = { onExport(s.id) }) {
                    Text(stringResource(R.string.session_export))
                }
            } ?: run {
                Text(
                    stringResource(R.string.session_no_sessions),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
    }
}
