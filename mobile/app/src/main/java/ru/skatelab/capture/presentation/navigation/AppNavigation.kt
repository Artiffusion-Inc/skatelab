package ru.skatelab.capture.presentation.navigation

import android.os.Environment
import androidx.compose.runtime.Composable
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import java.io.File
import ru.skatelab.capture.presentation.SessionState
import ru.skatelab.capture.presentation.ble.BleScanScreen
import ru.skatelab.capture.presentation.ble.BleScanViewModel
import ru.skatelab.capture.presentation.calibration.CalibrationScreen
import ru.skatelab.capture.presentation.calibration.CalibrationViewModel
import ru.skatelab.capture.presentation.export.ExportScreen
import ru.skatelab.capture.presentation.export.ExportViewModel
import ru.skatelab.capture.presentation.recording.RecordingScreen
import ru.skatelab.capture.presentation.sessiondetail.SessionDetailScreen
import ru.skatelab.capture.presentation.sessiondetail.SessionDetailViewModel
import ru.skatelab.capture.presentation.recording.RecordingViewModel
import ru.skatelab.capture.presentation.session.SessionListScreen
import ru.skatelab.capture.presentation.session.SessionListViewModel

object Routes {
    const val BLE_SCAN = "ble_scan"
    const val CALIBRATION = "calibration"
    const val RECORDING = "recording"
    const val EXPORT = "export/{sessionId}"
    const val SESSIONS = "sessions"
    const val SESSION_DETAIL = "session_detail/{sessionId}"

    fun export(sessionId: String) = "export/$sessionId"
    fun sessionDetail(sessionId: String) = "session_detail/$sessionId"
}

@InstallIn(SingletonComponent::class)
@EntryPoint
interface SessionStateEntryPoint {
    fun sessionState(): SessionState
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = Routes.SESSIONS,
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
            val outputDir =
                File(
                    context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS),
                    "skatelab_capture_${System.currentTimeMillis()}",
                ).also {
                    it.mkdirs()
                }
            val sessionState =
                EntryPointAccessors.fromApplication(
                    context.applicationContext,
                    SessionStateEntryPoint::class.java,
                ).sessionState()

            RecordingScreen(
                viewModel = viewModel,
                outputDir = outputDir,
                calibration = sessionState.calibration,
                onRecordingComplete = { sessionId ->
                    navController.navigate(Routes.sessionDetail(sessionId)) {
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

        composable(
            route = Routes.SESSION_DETAIL,
            arguments = listOf(navArgument("sessionId") { type = NavType.StringType }),
        ) { backStackEntry ->
            val sessionId = backStackEntry.arguments?.getString("sessionId") ?: ""
            val viewModel: SessionDetailViewModel = hiltViewModel()
            SessionDetailScreen(
                viewModel = viewModel,
                sessionId = sessionId,
                onBack = { navController.popBackStack() },
                onExport = { navController.navigate(Routes.export(it)) },
            )
        }

        composable(Routes.SESSIONS) {
            val viewModel: SessionListViewModel = hiltViewModel()
            SessionListScreen(
                viewModel = viewModel,
                onSessionClick = { sessionId ->
                    navController.navigate(Routes.sessionDetail(sessionId))
                },
                onExportSession = { sessionId ->
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
