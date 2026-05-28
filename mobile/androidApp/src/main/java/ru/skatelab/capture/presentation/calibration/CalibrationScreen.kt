package ru.skatelab.capture.presentation.calibration

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import java.util.Locale
import ru.skatelab.capture.R
import ru.skatelab.capture.domain.model.SensorId

private const val CALIBRATION_SECONDS = 10

@Composable
fun CalibrationScreen(
    viewModel: CalibrationViewModel,
    onProceed: () -> Unit,
) {
    val leftCal by viewModel.leftCalibration.collectAsState()
    val rightCal by viewModel.rightCalibration.collectAsState()
    val isCalibrating by viewModel.isCalibrating.collectAsState()
    val calibrationProgress by viewModel.calibrationProgress.collectAsState()
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

        SensorStatusCard(
            label = stringResource(R.string.calibration_left),
            calibration = leftCal,
            quaternion = leftQuat,
        )
        Spacer(modifier = Modifier.height(12.dp))
        SensorStatusCard(
            label = stringResource(R.string.calibration_right),
            calibration = rightCal,
            quaternion = rightQuat,
        )

        error?.let {
            Spacer(modifier = Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }

        Spacer(modifier = Modifier.height(24.dp))
        if (isCalibrating) {
            val secondsLeft = CALIBRATION_SECONDS - (calibrationProgress * CALIBRATION_SECONDS / 100)
            LinearProgressIndicator(
                progress = { calibrationProgress / 100f },
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = stringResource(R.string.calibration_countdown, secondsLeft),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Button(
            onClick = { viewModel.calibrateBoth() },
            enabled = !isCalibrating,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.calibration_calibrate_both))
        }

        Spacer(modifier = Modifier.weight(1f))
        Button(
            onClick = onProceed,
            enabled = !isCalibrating && (leftCal != null || rightCal != null),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.calibration_proceed))
        }
        Spacer(modifier = Modifier.height(8.dp))
        if (isCalibrating) {
            TextButton(
                onClick = { viewModel.cancelCalibration() },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.calibration_cancel))
            }
        } else {
            TextButton(
                onClick = onProceed,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.calibration_skip))
            }
        }
    }
}

@Composable
private fun SensorStatusCard(
    label: String,
    calibration: ru.skatelab.capture.domain.model.CalibrationData?,
    quaternion: QuaternionPreview,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(label, style = MaterialTheme.typography.titleMedium)

            val hasNonZero =
                quaternion.w != 0f || quaternion.x != 0f ||
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
            }
        }
    }
}

private fun Float.formatF(): String = String.format(Locale.US, "%.3f", this)
