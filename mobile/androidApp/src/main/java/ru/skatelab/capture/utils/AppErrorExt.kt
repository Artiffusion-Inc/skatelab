package ru.skatelab.capture.utils

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import ru.skatelab.capture.R
import ru.skatelab.shared.models.AppError

@Composable
fun AppError.asString(): String =
    stringResource(
        when (this) {
            is AppError.Network -> R.string.error_network
            is AppError.Auth -> R.string.error_auth
            is AppError.NotFound -> R.string.error_not_found
            is AppError.Server -> R.string.error_server
            is AppError.Timeout -> R.string.error_timeout
            is AppError.Unknown -> R.string.error_unknown
        },
    )
