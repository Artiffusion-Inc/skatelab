package ru.skatelab.capture.navigation

import kotlinx.serialization.Serializable

// --- Auth flow ---
@Serializable object SplashRoute

@Serializable object LoginRoute

@Serializable object RegisterRoute

@Serializable object ForgotPasswordRoute

@Serializable data class NewPasswordRoute(val token: String)

@Serializable data class VerifyEmailRoute(val token: String = "")

// --- Main app flow ---
@Serializable object CameraRoute

@Serializable object DashboardRoute

@Serializable object SessionsRoute

@Serializable data class ResultDetailRoute(
    val sessionId: String,
)

@Serializable data class MetricTrendRoute(
    val metricName: String,
    val elementType: String,
)

@Serializable data class ProcessingRoute(
    val uploadId: String? = null,
    val sessionId: String? = null,
)

@Serializable object UploadQueueRoute

@Serializable object ProfileRoute

@Serializable object MoreRoute

// --- IMU capture flow (existing) ---
@Serializable object BleScanRoute

@Serializable object CalibrationRoute

@Serializable object RecordingRoute
