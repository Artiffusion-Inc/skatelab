package ru.skatelab.capture

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import dagger.hilt.android.AndroidEntryPoint
import ru.skatelab.capture.presentation.navigation.AppNavigation
import ru.skatelab.capture.presentation.theme.AppTheme

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AppTheme {
                PermissionGate {
                    AppNavigation()
                }
            }
        }
    }
}

@Composable
private fun PermissionGate(content: @Composable () -> Unit) {
    val runtimePermissions =
        buildList {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(Manifest.permission.BLUETOOTH_SCAN)
                add(Manifest.permission.BLUETOOTH_CONNECT)
            } else {
                add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
            add(Manifest.permission.CAMERA)
        }

    var runtimeGranted by remember { mutableStateOf(false) }
    var requesting by remember { mutableStateOf(false) }
    val context = androidx.compose.ui.platform.LocalContext.current

    val runtimeLauncher =
        rememberLauncherForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions(),
        ) { results ->
            requesting = false
            runtimeGranted = results.all { it.value }
            if (!runtimeGranted) Log.w("MainActivity", "Denied: ${results.filter { !it.value }.keys}")
        }

    LaunchedEffect(Unit) {
        val missing =
            runtimePermissions.filter {
                ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
            }
        if (missing.isEmpty()) {
            runtimeGranted = true
        } else {
            requesting = true
            runtimeLauncher.launch(missing.toTypedArray())
        }
    }

    if (runtimeGranted) {
        content()
    } else {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Text(
                    stringResource(R.string.permissions_required),
                    style = MaterialTheme.typography.bodyLarge,
                )
                Spacer(Modifier.height(16.dp))
                if (requesting) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp))
                } else {
                    Button(
                        onClick = {
                            val missing =
                                runtimePermissions.filter {
                                    ContextCompat.checkSelfPermission(
                                        context,
                                        it,
                                    ) != PackageManager.PERMISSION_GRANTED
                                }
                            if (missing.isEmpty()) {
                                runtimeGranted = true
                            } else {
                                requesting = true
                                runtimeLauncher.launch(missing.toTypedArray())
                            }
                        },
                    ) {
                        Text(stringResource(R.string.permissions_grant))
                    }
                }
            }
        }
    }
}
