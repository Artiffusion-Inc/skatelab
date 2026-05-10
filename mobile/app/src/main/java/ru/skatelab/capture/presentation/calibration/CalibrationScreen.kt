package ru.skatelab.capture.presentation.calibration

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.SensorId

@Composable
fun CalibrationScreen(
    viewModel: CalibrationViewModel,
    onProceed: () -> Unit,
) {
    val leftCal by viewModel.leftCalibration.collectAsState()
    val rightCal by viewModel.rightCalibration.collectAsState()
    val isCalibrating by viewModel.isCalibrating.collectAsState()
    val error by viewModel.error.collectAsState()

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(stringResource(R.string.calibration_title), style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))

        Text(stringResource(R.string.calibration_instruction), style = MaterialTheme.typography.bodyMedium)
        Spacer(modifier = Modifier.height(24.dp))

        SensorCalibCard(stringResource(R.string.calibration_left), SensorId.LEFT, leftCal, isCalibrating) {
            viewModel.calibrate(SensorId.LEFT)
        }
        Spacer(modifier = Modifier.height(12.dp))
        SensorCalibCard(stringResource(R.string.calibration_right), SensorId.RIGHT, rightCal, isCalibrating) {
            viewModel.calibrate(SensorId.RIGHT)
        }

        error?.let {
            Spacer(modifier = Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }

        Spacer(modifier = Modifier.weight(1f))
        Button(
            onClick = onProceed,
            enabled = leftCal != null || rightCal != null,
        ) {
            Text(stringResource(R.string.calibration_proceed))
        }
    }
}

@Composable
private fun SensorCalibCard(
    label: String,
    sensorId: SensorId,
    calibration: ru.skatelab.capture.domain.model.CalibrationData?,
    isCalibrating: Boolean,
    onCalibrate: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(label, style = MaterialTheme.typography.titleMedium)
            if (calibration != null) {
                Text(stringResource(R.string.calibration_done), color = MaterialTheme.colorScheme.primary)
            } else {
                Button(onClick = onCalibrate, enabled = !isCalibrating) {
                    if (isCalibrating) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                        Spacer(modifier = Modifier.width(8.dp))
                    }
                    Text(stringResource(R.string.calibration_calibrate))
                }
            }
        }
    }
}
