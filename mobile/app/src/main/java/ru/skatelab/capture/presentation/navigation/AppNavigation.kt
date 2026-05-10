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
import ru.skatelab.capture.presentation.export.ExportScreen
import ru.skatelab.capture.presentation.export.ExportViewModel
import ru.skatelab.capture.presentation.recording.RecordingScreen
import ru.skatelab.capture.presentation.recording.RecordingViewModel
import ru.skatelab.capture.presentation.session.SessionListScreen
import ru.skatelab.capture.presentation.session.SessionListViewModel
import ru.skatelab.capture.presentation.SessionState
import java.io.File

object Routes {
    const val BLE_SCAN = "ble_scan"
    const val CALIBRATION = "calibration"
    const val RECORDING = "recording"
    const val EXPORT = "export/{sessionId}"
    const val SESSIONS = "sessions"

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
                onProceed = { navController.navigate(Routes.RECORDING) },
            )
        }

        composable(Routes.RECORDING) {
            val viewModel: RecordingViewModel = hiltViewModel()
            val context = androidx.compose.ui.platform.LocalContext.current
            val downloadsDir = android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_DOWNLOADS)
            val outputDir = File(downloadsDir, "skatelab_capture_${System.currentTimeMillis()}")

            RecordingScreen(
                viewModel = viewModel,
                outputDir = outputDir,
                calibration = SessionState.calibration,
                onRecordingComplete = { sessionId ->
                    navController.navigate(Routes.export(sessionId)) {
                        popUpTo(Routes.SESSIONS) { inclusive = false }
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
                onExportComplete = {
                    navController.navigate(Routes.SESSIONS) {
                        popUpTo(Routes.SESSIONS) { inclusive = true }
                    }
                },
            )
        }

        composable(Routes.SESSIONS) {
            val viewModel: SessionListViewModel = hiltViewModel()
            SessionListScreen(
                viewModel = viewModel,
                onSessionClick = { sessionId ->
                    navController.navigate(Routes.export(sessionId))
                },
                onNewRecording = {
                    navController.navigate(Routes.BLE_SCAN) {
                        popUpTo(Routes.SESSIONS) { inclusive = true }
                    }
                },
            )
        }
    }
}
