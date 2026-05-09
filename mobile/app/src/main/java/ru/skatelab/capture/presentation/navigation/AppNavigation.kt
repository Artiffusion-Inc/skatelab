package ru.skatelab.capture.presentation.navigation

import androidx.compose.runtime.Composable
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import ru.skatelab.capture.presentation.ble.BleScanScreen
import ru.skatelab.capture.presentation.ble.BleScanViewModel
import ru.skatelab.capture.presentation.calibration.CalibrationScreen
import ru.skatelab.capture.presentation.calibration.CalibrationViewModel
import ru.skatelab.capture.presentation.camera.CameraPreviewScreen
import ru.skatelab.capture.presentation.camera.CameraViewModel
import ru.skatelab.capture.presentation.export.ExportScreen
import ru.skatelab.capture.presentation.export.ExportViewModel
import ru.skatelab.capture.presentation.recording.RecordingScreen
import ru.skatelab.capture.presentation.recording.RecordingViewModel

object Routes {
    const val BLE_SCAN = "ble_scan"
    const val CALIBRATION = "calibration"
    const val CAMERA_PREVIEW = "camera_preview"
    const val RECORDING = "recording"
    const val EXPORT = "export/{sessionId}"

    fun export(sessionId: String) = "export/$sessionId"
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = Routes.BLE_SCAN,
    ) {
        composable(Routes.BLE_SCAN) {
            val viewModel: BleScanViewModel = hiltViewModel()
            BleScanScreen(
                viewModel = viewModel,
                onProceed = { navController.navigate(Routes.CALIBRATION) },
            )
        }

        composable(Routes.CALIBRATION) {
            val viewModel: CalibrationViewModel = hiltViewModel()
            CalibrationScreen(
                viewModel = viewModel,
                onProceed = { navController.navigate(Routes.CAMERA_PREVIEW) },
            )
        }

        composable(Routes.CAMERA_PREVIEW) {
            val viewModel: CameraViewModel = hiltViewModel()
            CameraPreviewScreen(
                viewModel = viewModel,
                onStartRecording = { navController.navigate(Routes.RECORDING) },
            )
        }

        composable(Routes.RECORDING) {
            val viewModel: RecordingViewModel = hiltViewModel()
            RecordingScreen(
                viewModel = viewModel,
                onStop = { sessionId ->
                    navController.navigate(Routes.export(sessionId)) {
                        popUpTo(Routes.CAMERA_PREVIEW) { inclusive = false }
                    }
                },
            )
        }

        composable(
            route = Routes.EXPORT,
            arguments = listOf(navArgument("sessionId") { type = NavType.StringType }),
        ) { backStackEntry ->
            val sessionId = backStackEntry.arguments?.getString("sessionId") ?: ""
            val viewModel: ExportViewModel = hiltViewModel()
            ExportScreen(
                viewModel = viewModel,
                sessionId = sessionId,
            )
        }
    }
}
