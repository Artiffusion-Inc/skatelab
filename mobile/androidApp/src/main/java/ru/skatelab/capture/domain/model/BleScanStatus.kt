package ru.skatelab.capture.domain.model

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
