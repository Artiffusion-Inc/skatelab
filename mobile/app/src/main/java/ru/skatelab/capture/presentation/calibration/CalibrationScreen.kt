package ru.skatelab.capture.presentation.calibration

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
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
    val leftQuat by viewModel.leftQuat.collectAsState()
    val rightQuat by viewModel.rightQuat.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.startPreview(SensorId.LEFT)
        viewModel.startPreview(SensorId.RIGHT)
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(stringResource(R.string.calibration_title), style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(16.dp))

        Text(stringResource(R.string.calibration_instruction), style = MaterialTheme.typography.bodyMedium)
        Spacer(modifier = Modifier.height(24.dp))

        SensorCalibCard(
            label = stringResource(R.string.calibration_left),
            sensorId = SensorId.LEFT,
            calibration = leftCal,
            quaternion = leftQuat,
            isCalibrating = isCalibrating,
            onCalibrate = { viewModel.calibrate(SensorId.LEFT) },
        )
        Spacer(modifier = Modifier.height(12.dp))
        SensorCalibCard(
            label = stringResource(R.string.calibration_right),
            sensorId = SensorId.RIGHT,
            calibration = rightCal,
            quaternion = rightQuat,
            isCalibrating = isCalibrating,
            onCalibrate = { viewModel.calibrate(SensorId.RIGHT) },
        )

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
    quaternion: QuaternionPreview,
    isCalibrating: Boolean,
    onCalibrate: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(label, style = MaterialTheme.typography.titleMedium)

            // Live quaternion preview
            val hasNonZero = quaternion.w != 0f || quaternion.x != 0f ||
                quaternion.y != 0f || quaternion.z != 0f
            if (hasNonZero) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "q=[${quaternion.w.formatF()}, ${quaternion.x.formatF()}, ${quaternion.y.formatF()}, ${quaternion.z.formatF()}]",
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            if (calibration != null) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(stringResource(R.string.calibration_done), color = MaterialTheme.colorScheme.primary)
            } else {
                Spacer(modifier = Modifier.height(8.dp))
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

private fun Float.formatF(): String = String.format("%.3f", this)
