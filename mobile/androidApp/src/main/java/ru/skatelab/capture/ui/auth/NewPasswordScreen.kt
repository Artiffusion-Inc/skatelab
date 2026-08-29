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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.utils.localizedMessage
import ru.skatelab.shared.state.NewPasswordUiState

@Composable
fun NewPasswordScreen(
    token: String,
    uiState: NewPasswordUiState,
    onResetPassword: (token: String, newPassword: String) -> Unit,
    onNavigateToLogin: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var password by rememberSaveable { mutableStateOf("") }
    var confirmation by rememberSaveable { mutableStateOf("") }
    val busy = uiState is NewPasswordUiState.Loading
    val mismatch = confirmation.isNotEmpty() && password != confirmation

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
            text = stringResource(R.string.auth_new_password_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.auth_new_password_subtitle),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(24.dp))

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text(stringResource(R.string.auth_new_password_label)) },
            singleLine = true,
            enabled = !busy,
            isError = mismatch || uiState is NewPasswordUiState.Error,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = confirmation,
            onValueChange = { confirmation = it },
            label = { Text(stringResource(R.string.auth_confirm_password)) },
            singleLine = true,
            enabled = !busy,
            isError = mismatch || uiState is NewPasswordUiState.Error,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )

        if (mismatch) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResource(R.string.auth_password_mismatch),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        }

        Spacer(Modifier.height(16.dp))
        when (uiState) {
            NewPasswordUiState.Idle -> Unit
            NewPasswordUiState.Loading -> CircularProgressIndicator()
            NewPasswordUiState.Success ->
                Text(
                    text = stringResource(R.string.auth_new_password_success),
                    color = MaterialTheme.colorScheme.primary,
                )
            is NewPasswordUiState.Error ->
                Text(
                    text = uiState.error.localizedMessage(),
                    color = MaterialTheme.colorScheme.error,
                )
        }

        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { onResetPassword(token.trim(), password) },
            enabled = token.isNotBlank() && password.length >= 8 && !mismatch && !busy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.auth_new_password_button))
        }
        TextButton(onClick = onBack, enabled = !busy) {
            Text(stringResource(R.string.auth_back_to_login))
        }
        if (uiState is NewPasswordUiState.Success) {
            TextButton(onClick = onNavigateToLogin) {
                Text(stringResource(R.string.auth_back_to_login))
            }
        }
    }
}
