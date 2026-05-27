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
import androidx.compose.ui.semantics.LiveRegion
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.BleScanStatus
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository.ConnectionState
import ru.skatelab.capture.domain.repository.ScanDevice

@Composable
fun BleScanScreen(
    viewModel: BleScanViewModel,
    onProceed: () -> Unit,
) {
    val scanResults by viewModel.scanResults.collectAsState()
    val connectionState by viewModel.connectionState.collectAsState()
    val scanStatus by viewModel.scanStatus.collectAsState()

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
                    leftConnected =
                        connectionState[SensorId.LEFT] != null &&
                            connectionState[SensorId.LEFT] != ConnectionState.DISCONNECTED,
                    rightConnected =
                        connectionState[SensorId.RIGHT] != null &&
                            connectionState[SensorId.RIGHT] != ConnectionState.DISCONNECTED,
                    leftSensorAddress =
                        connectionState.entries
                            .find { it.key == SensorId.LEFT && it.value != ConnectionState.DISCONNECTED }
                            ?.let { viewModel.getAddressForSensor(SensorId.LEFT) },
                    rightSensorAddress =
                        connectionState.entries
                            .find { it.key == SensorId.RIGHT && it.value != ConnectionState.DISCONNECTED }
                            ?.let { viewModel.getAddressForSensor(SensorId.RIGHT) },
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

        scanStatus?.let { status ->
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                status.asString(),
                style = MaterialTheme.typography.bodySmall,
                color = if (status.isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                modifier = Modifier.semantics { liveRegion = LiveRegion.Polite },
            )
        }
    }
}

@Composable
private fun ScanDeviceRow(
    device: ScanDevice,
    leftConnected: Boolean,
    rightConnected: Boolean,
    leftSensorAddress: String?,
    rightSensorAddress: String?,
    onConnectLeft: () -> Unit,
    onConnectRight: () -> Unit,
    onFactoryResetLeft: () -> Unit,
    onFactoryResetRight: () -> Unit,
    onAccCalibrateLeft: () -> Unit,
    onAccCalibrateRight: () -> Unit,
) {
    // Is this device the one assigned to LEFT or RIGHT sensor?
    val isLeftDevice = leftSensorAddress == device.address
    val isRightDevice = rightSensorAddress == device.address

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
                    if (device.isConnected) {
                        Text(stringResource(R.string.ble_connected), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                    } else {
                        Text(stringResource(R.string.ble_rssi, device.rssi), style = MaterialTheme.typography.bodySmall)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    OutlinedButton(onClick = onConnectLeft, enabled = !leftConnected) { Text(stringResource(R.string.ble_left)) }
                    OutlinedButton(onClick = onConnectRight, enabled = !rightConnected) { Text(stringResource(R.string.ble_right)) }
                }
            }
            // Show control buttons only for the sensor assigned to THIS device
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                if (isLeftDevice) {
                    TextButton(onClick = onFactoryResetLeft) {
                        Text(stringResource(R.string.ble_reset_left), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
                    }
                    TextButton(onClick = onAccCalibrateLeft) {
                        Text(stringResource(R.string.ble_acc_left), color = MaterialTheme.colorScheme.tertiary, style = MaterialTheme.typography.labelSmall)
                    }
                }
                if (isRightDevice) {
                    TextButton(onClick = onFactoryResetRight) {
                        Text(stringResource(R.string.ble_reset_right), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
                    }
                    TextButton(onClick = onAccCalibrateRight) {
                        Text(stringResource(R.string.ble_acc_right), color = MaterialTheme.colorScheme.tertiary, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
