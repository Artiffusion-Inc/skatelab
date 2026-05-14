package ru.skatelab.capture.presentation.ble

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository.ConnectionState
import ru.skatelab.capture.domain.repository.ScanDevice

@Composable
fun BleScanScreen(
    viewModel: BleScanViewModel,
    onProceed: () -> Unit,
) {
    val scanResults by viewModel.scanResults.collectAsState()
    val connectionState by viewModel.connectionState.collectAsState()
    val factoryResetStatus by viewModel.factoryResetStatus.collectAsState()
    val sensorInfo by viewModel.sensorInfo.collectAsState()

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
                    leftInfo = sensorInfo[SensorId.LEFT],
                    rightInfo = sensorInfo[SensorId.RIGHT],
                    leftConnected =
                        connectionState[SensorId.LEFT] != null &&
                            connectionState[SensorId.LEFT] != ConnectionState.DISCONNECTED,
                    rightConnected =
                        connectionState[SensorId.RIGHT] != null &&
                            connectionState[SensorId.RIGHT] != ConnectionState.DISCONNECTED,
                    onConnectLeft = { viewModel.connectSensor(SensorId.LEFT, device.address) },
                    onConnectRight = { viewModel.connectSensor(SensorId.RIGHT, device.address) },
                    onFactoryResetLeft = { viewModel.factoryResetSensor(SensorId.LEFT) },
                    onFactoryResetRight = { viewModel.factoryResetSensor(SensorId.RIGHT) },
                    onAccCalibrateLeft = { viewModel.accCalibrateSensor(SensorId.LEFT) },
                    onAccCalibrateRight = { viewModel.accCalibrateSensor(SensorId.RIGHT) },
                )
            }
        }

        val anyConnected =
            connectionState[SensorId.LEFT] == ConnectionState.CONNECTED ||
                connectionState[SensorId.RIGHT] == ConnectionState.CONNECTED

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
    leftInfo: SensorInfo? = null,
    rightInfo: SensorInfo? = null,
    leftConnected: Boolean,
    rightConnected: Boolean,
    onConnectLeft: () -> Unit,
    onConnectRight: () -> Unit,
    onFactoryResetLeft: (() -> Unit)? = null,
    onFactoryResetRight: (() -> Unit)? = null,
    onAccCalibrateLeft: (() -> Unit)? = null,
    onAccCalibrateRight: (() -> Unit)? = null,
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
            // Factory reset and ACC calibration buttons for connected sensors
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
                if (leftConnected && onAccCalibrateLeft != null) {
                    TextButton(onClick = onAccCalibrateLeft) {
                        Text("ACC лев.", color = MaterialTheme.colorScheme.tertiary, style = MaterialTheme.typography.labelSmall)
                    }
                }
                if (rightConnected && onAccCalibrateRight != null) {
                    TextButton(onClick = onAccCalibrateRight) {
                        Text("ACC прав.", color = MaterialTheme.colorScheme.tertiary, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            if (leftInfo != null) {
                SensorInfoRow(info = leftInfo, label = "Левый")
            }
            if (rightInfo != null) {
                SensorInfoRow(info = rightInfo, label = "Правый")
            }
        }
    }
}

@Composable
private fun SensorInfoRow(
    info: SensorInfo,
    label: String,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            "$label: ${info.batteryPercent}% (${info.batteryMv}mV)",
            style = MaterialTheme.typography.labelSmall,
        )
        Text(
            "ID:${info.deviceId.takeLast(4)} FW:${info.firmwareVersion}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
