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
            is AppError.Conflict -> R.string.error_conflict
            is AppError.Unknown -> R.string.error_unknown
        },
    )

/**
 * Locale-aware error message mirroring [LoginScreen]'s dispatch (#405).
 *
 * Surfaces the actionable [AppError.Conflict.detail] / [AppError.Unknown.detail] when present
 * (e.g. "Email already registered"), falling back to the localized generic message otherwise.
 * Use this in Compose instead of rendering the raw [AppError.messageKey] key.
 */
@Composable
fun AppError.localizedMessage(): String =
    when (this) {
        is AppError.Network -> stringResource(R.string.error_network)
        is AppError.Auth -> stringResource(R.string.error_auth)
        is AppError.NotFound -> stringResource(R.string.error_not_found)
        is AppError.Server -> stringResource(R.string.error_server)
        is AppError.Conflict -> detail ?: stringResource(R.string.error_conflict)
        is AppError.Timeout -> stringResource(R.string.error_timeout)
        is AppError.Unknown -> detail ?: stringResource(R.string.error_unknown)
    }
