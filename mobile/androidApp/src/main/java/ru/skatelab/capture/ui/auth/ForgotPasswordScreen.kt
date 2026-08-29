package ru.skatelab.capture.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.utils.localizedMessage
import ru.skatelab.shared.state.PasswordRecoveryUiState

@Composable
fun ForgotPasswordScreen(
    uiState: PasswordRecoveryUiState,
    onRequestReset: (String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var email by rememberSaveable { mutableStateOf("") }
    val busy = uiState is PasswordRecoveryUiState.Loading

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(stringResource(R.string.auth_forgot_title), style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(8.dp))
        Text(stringResource(R.string.auth_forgot_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(24.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text(stringResource(R.string.auth_email)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            singleLine = true,
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(16.dp))
        when (uiState) {
            PasswordRecoveryUiState.Loading -> CircularProgressIndicator()
            PasswordRecoveryUiState.Sent -> Text(stringResource(R.string.auth_forgot_sent), color = MaterialTheme.colorScheme.primary)
            is PasswordRecoveryUiState.Error -> Text(uiState.error.localizedMessage(), color = MaterialTheme.colorScheme.error)
            PasswordRecoveryUiState.Idle -> Unit
        }
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { onRequestReset(email) },
            enabled = email.isNotBlank() && !busy,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.auth_forgot_button)) }
        TextButton(onClick = onBack, enabled = !busy) {
            Text(stringResource(R.string.auth_back_to_login))
        }
    }
}
