package ru.skatelab.capture.ui.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.state.AuthUiState

private fun isNetworkError(message: String): Boolean {
    val lower = message.lowercase()
    return lower.contains("network") || lower.contains("connection") ||
        lower.contains("timeout") || lower.contains("socket") ||
        lower.contains("unreachable") || lower.contains("resolve") ||
        lower.contains("connectexception") || lower.contains("ioexception") ||
        lower.contains("unable to resolve host") || lower.contains("connection reset") ||
        lower.contains("connection refused")
}

@Composable
fun LoginScreen(
    uiState: AuthUiState,
    onLogin: (email: String, password: String) -> Unit,
    onNavigateToRegister: () -> Unit,
    onNavigateToCamera: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(uiState) {
        if (uiState is AuthUiState.LoggedIn) {
            onNavigateToCamera()
        }
    }

    Column(
        modifier =
            modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "OOFSkate",
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.auth_login_title),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text(stringResource(R.string.auth_email)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth(),
            enabled = uiState !is AuthUiState.Loading,
            isError = uiState is AuthUiState.Error,
        )
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text(stringResource(R.string.auth_password)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
            enabled = uiState !is AuthUiState.Loading,
            isError = uiState is AuthUiState.Error,
        )
        Spacer(Modifier.height(8.dp))

        if (uiState is AuthUiState.Error) {
            val msg = uiState.error.messageKey
            val displayMsg =
                if (isNetworkError(msg)) {
                    stringResource(R.string.auth_no_network)
                } else {
                    msg
                }
            Text(
                text = displayMsg,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(8.dp))
            OutlinedButton(
                onClick = { onLogin(email.trim(), password) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.auth_retry))
            }
        }

        Spacer(Modifier.height(16.dp))

        when (uiState) {
            is AuthUiState.Loading -> {
                val context = LocalContext.current
                Box(
                    modifier =
                        Modifier
                            .semantics(mergeDescendants = true) {
                                contentDescription = context.getString(R.string.cd_loading)
                                role = Role.ValuePicker
                            },
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp))
                }
            }
            is AuthUiState.Error -> { /* error block already shown above */ }
            else -> {
                Button(
                    onClick = { onLogin(email.trim(), password) },
                    enabled = email.isNotBlank() && password.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().testTag("loginButton"),
                ) {
                    Text(stringResource(R.string.auth_login_button))
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        TextButton(onClick = onNavigateToRegister) {
            Text(stringResource(R.string.auth_no_account))
        }
    }
}
