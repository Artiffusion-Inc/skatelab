package ru.skatelab.capture.presentation.ble

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.ScanDevice

@Composable
fun BleScanScreen(
    viewModel: BleScanViewModel,
    onProceed: () -> Unit,
) {
    val scanResults by viewModel.scanResults.collectAsState()
    val connectionState by viewModel.connectionState.collectAsState()
    val factoryResetStatus by viewModel.factoryResetStatus.collectAsState()

    LaunchedEffect(Unit) { viewModel.startScan() }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(stringResource(R.string.ble_scan_title), style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { viewModel.startScan() }) { Text(stringResource(R.string.ble_scan_button)) }
            Button(onClick = { viewModel.stopScan() }) { Text(stringResource(R.string.ble_scan_stop)) }
        }
        Spacer(modifier = Modifier.height(16.dp))

        LazyColumn(modifier = Modifier.weight(1f)) {
            items(scanResults) { device ->
                ScanDeviceRow(
                    device = device,
                    leftConnected = connectionState[SensorId.LEFT] != null &&
                        connectionState[SensorId.LEFT] != ru.skatelab.capture.domain.repository.BleRepository.ConnectionState.DISCONNECTED,
                    rightConnected = connectionState[SensorId.RIGHT] != null &&
                        connectionState[SensorId.RIGHT] != ru.skatelab.capture.domain.repository.BleRepository.ConnectionState.DISCONNECTED,
                    onConnectLeft = { viewModel.connectSensor(SensorId.LEFT, device.address) },
                    onConnectRight = { viewModel.connectSensor(SensorId.RIGHT, device.address) },
                    onFactoryResetLeft = { viewModel.factoryResetSensor(SensorId.LEFT) },
                    onFactoryResetRight = { viewModel.factoryResetSensor(SensorId.RIGHT) },
                )
            }
        }

        val anyConnected = connectionState[SensorId.LEFT] == ru.skatelab.capture.domain.repository.BleRepository.ConnectionState.CONNECTED ||
            connectionState[SensorId.RIGHT] == ru.skatelab.capture.domain.repository.BleRepository.ConnectionState.CONNECTED

        Button(onClick = onProceed, enabled = anyConnected) {
            Text(stringResource(R.string.ble_proceed_calibration))
        }

        factoryResetStatus?.let {
            Spacer(modifier = Modifier.height(8.dp))
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun ScanDeviceRow(
    device: ScanDevice,
    leftConnected: Boolean,
    rightConnected: Boolean,
    onConnectLeft: () -> Unit,
    onConnectRight: () -> Unit,
    onFactoryResetLeft: (() -> Unit)? = null,
    onFactoryResetRight: (() -> Unit)? = null,
) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(device.name, style = MaterialTheme.typography.bodyLarge)
                    Text(device.address, style = MaterialTheme.typography.bodySmall)
                    Text("RSSI: ${device.rssi}", style = MaterialTheme.typography.bodySmall)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    OutlinedButton(onClick = onConnectLeft, enabled = !leftConnected) { Text(stringResource(R.string.ble_left)) }
                    OutlinedButton(onClick = onConnectRight, enabled = !rightConnected) { Text(stringResource(R.string.ble_right)) }
                }
            }
            // Factory reset buttons for connected sensors
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                if (leftConnected && onFactoryResetLeft != null) {
                    TextButton(onClick = onFactoryResetLeft) {
                        Text("Сброс лев.", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
                    }
                }
                if (rightConnected && onFactoryResetRight != null) {
                    TextButton(onClick = onFactoryResetRight) {
                        Text("Сброс прав.", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
