package ru.skatelab.capture.ui.auth

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.SportsScore
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.utils.localizedMessage
import ru.skatelab.shared.state.AuthUiState

@Composable
fun LoginScreen(
    uiState: AuthUiState,
    onLogin: (email: String, password: String) -> Unit,
    onNavigateToRegister: () -> Unit,
    onNavigateToForgotPassword: () -> Unit,
    onNavigateToCamera: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(uiState) {
        if (uiState is AuthUiState.LoggedIn) {
            onNavigateToCamera()
        }
        // After logout (or any transition back to LoggedOut), clear the form so the
        // next login attempt starts from a fresh state — not a stale email/error
        // left over from the previous session (#327).
        if (uiState is AuthUiState.LoggedOut) {
            email = ""
            password = ""
        }
    }

    Column(
        modifier =
            modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Top,
    ) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onNavigateToRegister) {
                androidx.compose.material3.Icon(
                    Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = stringResource(R.string.auth_back),
                )
            }
            Text(
                text = stringResource(R.string.auth_login_heading),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(28.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.material3.Surface(
                shape = androidx.compose.foundation.shape.RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
            ) {
                androidx.compose.material3.Icon(
                    Icons.Outlined.SportsScore,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(14.dp).size(40.dp),
                )
            }
            Spacer(Modifier.size(12.dp))
            Column {
                Text(stringResource(R.string.splash_brand), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text(stringResource(R.string.auth_brand_subtitle), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Spacer(Modifier.height(36.dp))
        Text(
            text = stringResource(R.string.auth_login_title),
            style = MaterialTheme.typography.displaySmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(24.dp))

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text(stringResource(R.string.auth_email)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth().testTag("emailField"),
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
            modifier = Modifier.fillMaxWidth().testTag("passwordField"),
            enabled = uiState !is AuthUiState.Loading,
            isError = uiState is AuthUiState.Error,
        )
        Spacer(Modifier.height(8.dp))

        if (uiState is AuthUiState.Error) {
            val error = uiState.error
            val displayMsg = error.localizedMessage()
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

        TextButton(onClick = onNavigateToForgotPassword) {
            Text(stringResource(R.string.auth_forgot_link))
        }
        TextButton(onClick = onNavigateToRegister) {
            Text(stringResource(R.string.auth_no_account))
        }
    }
}
