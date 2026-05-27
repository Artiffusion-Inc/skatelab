package ru.skatelab.capture.domain.model

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import ru.skatelab.capture.R

enum class BleScanStatus {
    IDLE,
    RESETTING_LEFT,
    RESETTING_RIGHT,
    RESET_OK_LEFT,
    RESET_OK_RIGHT,
    RESET_FAILED,
    CALIBRATING_LEFT,
    CALIBRATING_RIGHT,
    CALIBRATION_OK_LEFT,
    CALIBRATION_OK_RIGHT,
    CALIBRATION_FAILED,
}

val BleScanStatus.isError: Boolean
    get() = this == BleScanStatus.RESET_FAILED || this == BleScanStatus.CALIBRATION_FAILED

@Composable
fun BleScanStatus.asString(): String =
    when (this) {
        BleScanStatus.IDLE -> stringResource(R.string.ble_status_idle)
        BleScanStatus.RESETTING_LEFT -> stringResource(R.string.ble_status_resetting_left)
        BleScanStatus.RESETTING_RIGHT -> stringResource(R.string.ble_status_resetting_right)
        BleScanStatus.RESET_OK_LEFT -> stringResource(R.string.ble_status_reset_ok_left)
        BleScanStatus.RESET_OK_RIGHT -> stringResource(R.string.ble_status_reset_ok_right)
        BleScanStatus.RESET_FAILED -> stringResource(R.string.ble_status_reset_failed)
        BleScanStatus.CALIBRATING_LEFT -> stringResource(R.string.ble_status_calibrating_left)
        BleScanStatus.CALIBRATING_RIGHT -> stringResource(R.string.ble_status_calibrating_right)
        BleScanStatus.CALIBRATION_OK_LEFT -> stringResource(R.string.ble_status_calibration_ok_left)
        BleScanStatus.CALIBRATION_OK_RIGHT -> stringResource(R.string.ble_status_calibration_ok_right)
        BleScanStatus.CALIBRATION_FAILED -> stringResource(R.string.ble_status_calibration_failed)
    }
