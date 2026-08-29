package ru.skatelab.capture.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
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
import ru.skatelab.shared.state.VerifyEmailUiState

@Composable
fun VerifyEmailScreen(
    token: String,
    uiState: VerifyEmailUiState,
    onVerifyEmail: (String) -> Unit,
    onResendVerification: (String) -> Unit,
    onNavigateToLogin: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var tokenValue by rememberSaveable(token) { mutableStateOf(token) }
    var email by rememberSaveable { mutableStateOf("") }
    val busy = uiState is VerifyEmailUiState.Loading
    val verified = uiState is VerifyEmailUiState.Verified

    Column(
        modifier =
            modifier
                .fillMaxSize()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = stringResource(R.string.auth_verify_email_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.auth_verify_email_subtitle),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(24.dp))

        OutlinedTextField(
            value = tokenValue,
            onValueChange = { tokenValue = it },
            label = { Text(stringResource(R.string.auth_verification_token)) },
            singleLine = true,
            enabled = !busy && !verified,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        Button(
            onClick = { onVerifyEmail(tokenValue.trim()) },
            enabled = tokenValue.isNotBlank() && !busy && !verified,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.auth_verify_email_button))
        }

        Spacer(Modifier.height(16.dp))
        when (uiState) {
            VerifyEmailUiState.Idle -> Unit
            VerifyEmailUiState.Loading -> CircularProgressIndicator()
            VerifyEmailUiState.Verified -> {
                Text(
                    text = stringResource(R.string.auth_email_verified),
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = onNavigateToLogin) {
                    Text(stringResource(R.string.auth_back_to_login))
                }
            }
            VerifyEmailUiState.Sent ->
                Text(
                    text = stringResource(R.string.auth_verification_sent),
                    color = MaterialTheme.colorScheme.primary,
                )
            is VerifyEmailUiState.Error ->
                Text(
                    text = uiState.error.localizedMessage(),
                    color = MaterialTheme.colorScheme.error,
                )
        }

        Spacer(Modifier.height(24.dp))
        Text(
            text = stringResource(R.string.auth_resend_verification_title),
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text(stringResource(R.string.auth_email)) },
            singleLine = true,
            enabled = !busy,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        TextButton(
            onClick = { onResendVerification(email.trim()) },
            enabled = email.isNotBlank() && !busy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.auth_resend_verification_button))
        }
        TextButton(onClick = onBack, enabled = !busy) {
            Text(stringResource(R.string.auth_back_to_login))
        }
    }
}
