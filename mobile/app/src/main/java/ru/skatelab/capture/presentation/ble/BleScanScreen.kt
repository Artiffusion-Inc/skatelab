package ru.skatelab.capture.presentation.ble

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.ScanDevice

@Composable
fun BleScanScreen(
    viewModel: BleScanViewModel,
    onProceed: () -> Unit,
) {
    val scanResults by viewModel.scanResults.collectAsState()
    val connectionState by viewModel.connectionState.collectAsState()

    LaunchedEffect(Unit) { viewModel.startScan() }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("BLE Sensor Scan", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { viewModel.startScan() }) { Text("Scan") }
            Button(onClick = { viewModel.stopScan() }) { Text("Stop") }
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
                )
            }
        }

        val anyConnected = connectionState[SensorId.LEFT] == ru.skatelab.capture.domain.repository.BleRepository.ConnectionState.CONNECTED ||
            connectionState[SensorId.RIGHT] == ru.skatelab.capture.domain.repository.BleRepository.ConnectionState.CONNECTED

        Button(onClick = onProceed, enabled = anyConnected) {
            Text("Proceed to Calibration")
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
) {
    Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            modifier = Modifier.padding(12.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(device.name, style = MaterialTheme.typography.bodyLarge)
                Text(device.address, style = MaterialTheme.typography.bodySmall)
                Text("RSSI: ${device.rssi}", style = MaterialTheme.typography.bodySmall)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                OutlinedButton(onClick = onConnectLeft, enabled = !leftConnected) { Text("Left") }
                OutlinedButton(onClick = onConnectRight, enabled = !rightConnected) { Text("Right") }
            }
        }
    }
}
