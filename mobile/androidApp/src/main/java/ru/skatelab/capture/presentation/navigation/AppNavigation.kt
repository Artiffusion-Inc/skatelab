package ru.skatelab.capture.presentation.navigation

import android.os.Environment
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import java.io.File
import ru.skatelab.capture.navigation.BleScanRoute
import ru.skatelab.capture.navigation.CalibrationRoute
import ru.skatelab.capture.navigation.CameraRoute
import ru.skatelab.capture.navigation.ExportRoute
import ru.skatelab.capture.navigation.LoginRoute
import ru.skatelab.capture.navigation.MetricTrendRoute
import ru.skatelab.capture.navigation.ProcessingRoute
import ru.skatelab.capture.navigation.RecordingRoute
import ru.skatelab.capture.navigation.RegisterRoute
import ru.skatelab.capture.navigation.ResultDetailRoute
import ru.skatelab.capture.navigation.SessionDetailRoute
import ru.skatelab.capture.navigation.SessionsRoute
import ru.skatelab.capture.navigation.SplashRoute
import ru.skatelab.capture.presentation.SessionState
import ru.skatelab.capture.presentation.ble.BleScanScreen
import ru.skatelab.capture.presentation.ble.BleScanViewModel
import ru.skatelab.capture.presentation.calibration.CalibrationScreen
import ru.skatelab.capture.presentation.calibration.CalibrationViewModel
import ru.skatelab.capture.presentation.export.ExportScreen
import ru.skatelab.capture.presentation.export.ExportViewModel
import ru.skatelab.capture.presentation.recording.RecordingScreen
import ru.skatelab.capture.presentation.recording.RecordingViewModel
import ru.skatelab.capture.presentation.session.SessionListScreen as LocalSessionListScreen
import ru.skatelab.capture.presentation.session.SessionListViewModel
import ru.skatelab.capture.presentation.sessiondetail.SessionDetailScreen as LocalSessionDetailScreen
import ru.skatelab.capture.presentation.sessiondetail.SessionDetailViewModel
import ru.skatelab.capture.ui.auth.AuthViewModel
import ru.skatelab.capture.ui.auth.LoginScreen
import ru.skatelab.capture.ui.auth.RegisterScreen
import ru.skatelab.capture.ui.auth.SplashScreen
import ru.skatelab.capture.ui.metrics.AndroidMetricTrendViewModel
import ru.skatelab.capture.ui.metrics.MetricTrendScreen
import ru.skatelab.capture.ui.processing.ProcessingScreen
import ru.skatelab.capture.ui.session.AndroidSessionDetailViewModel
import ru.skatelab.capture.ui.session.AndroidSessionsViewModel
import ru.skatelab.capture.ui.session.SessionDetailScreen as ResultDetailScreen
import ru.skatelab.capture.ui.session.SessionListScreen as ResultListScreen

@InstallIn(SingletonComponent::class)
@EntryPoint
interface SessionStateEntryPoint {
    fun sessionState(): SessionState
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val authViewModel: AuthViewModel = hiltViewModel()
    val authState by authViewModel.uiState.collectAsState()

    NavHost(
        navController = navController,
        startDestination = SplashRoute,
    ) {
        // --- Auth flow ---
        composable<SplashRoute> {
            SplashScreen(
                uiState = authState,
                onCheckLogin = { authViewModel.checkLogin() },
                onNavigateToLogin = {
                    navController.navigate(LoginRoute) {
                        popUpTo<SplashRoute> { inclusive = true }
                    }
                },
                onNavigateToCamera = {
                    navController.navigate(CameraRoute) {
                        popUpTo<SplashRoute> { inclusive = true }
                    }
                },
            )
        }

        composable<LoginRoute> {
            LoginScreen(
                uiState = authState,
                onLogin = { email, password -> authViewModel.login(email, password) },
                onNavigateToRegister = {
                    navController.navigate(RegisterRoute)
                },
                onNavigateToCamera = {
                    navController.navigate(CameraRoute) {
                        popUpTo<LoginRoute> { inclusive = true }
                    }
                },
            )
        }

        composable<RegisterRoute> {
            RegisterScreen(
                uiState = authState,
                onRegister = { email, password, displayName ->
                    authViewModel.register(email, password, displayName)
                },
                onNavigateToLogin = {
                    navController.popBackStack()
                },
                onNavigateToCamera = {
                    navController.navigate(CameraRoute) {
                        popUpTo<RegisterRoute> { inclusive = true }
                    }
                },
            )
        }

        // --- Main app (tabbed) ---
        composable<CameraRoute> {
            ru.skatelab.capture.ui.tabs.MainTabsScreen(
                onNavigateToBleScan = {
                    navController.navigate(BleScanRoute)
                },
                onLogout = {
                    navController.navigate(LoginRoute) {
                        popUpTo<SplashRoute> { inclusive = true }
                    }
                },
                onNavigateToSessionDetail = { sessionId ->
                    navController.navigate(ResultDetailRoute(sessionId))
                },
                onNavigateToMetricTrend = { metricName, elementType ->
                    navController.navigate(MetricTrendRoute(metricName, elementType))
                },
            )
        }

        // --- Processing (SSE progress) ---
        composable<ProcessingRoute> { backStackEntry ->
            val route = backStackEntry.toRoute<ProcessingRoute>()
            ProcessingScreen(
                videoKey = route.videoKey,
                sessionId = route.sessionId,
                onCompleted = { taskId ->
                    navController.navigate(ResultDetailRoute(taskId)) {
                        popUpTo<ProcessingRoute> { inclusive = true }
                    }
                },
                onBack = { navController.popBackStack() },
            )
        }

        // --- Results (server sessions) ---
        composable<ResultDetailRoute> { backStackEntry ->
            val route = backStackEntry.toRoute<ResultDetailRoute>()
            val viewModel: AndroidSessionDetailViewModel = hiltViewModel()
            ResultDetailScreen(
                viewModel = viewModel,
                sessionId = route.sessionId,
                onBack = { navController.popBackStack() },
                onNavigateToMetricTrend = { metricName, elementType ->
                    navController.navigate(MetricTrendRoute(metricName, elementType))
                },
            )
        }

        // --- Metric trend chart ---
        composable<MetricTrendRoute> { backStackEntry ->
            val route = backStackEntry.toRoute<MetricTrendRoute>()
            val viewModel: AndroidMetricTrendViewModel = hiltViewModel()
            MetricTrendScreen(
                viewModel = viewModel,
                metricName = route.metricName,
                elementType = route.elementType,
                onBack = { navController.popBackStack() },
            )
        }

        // --- IMU capture flow (existing) ---
        composable<BleScanRoute> {
            val viewModel: BleScanViewModel = hiltViewModel()
            BleScanScreen(
                viewModel = viewModel,
                onProceed = { navController.navigate(CalibrationRoute) },
            )
        }

        composable<CalibrationRoute> {
            val viewModel: CalibrationViewModel = hiltViewModel()
            CalibrationScreen(
                viewModel = viewModel,
                onProceed = { navController.navigate(RecordingRoute) },
            )
        }

        composable<RecordingRoute> {
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
                    navController.navigate(SessionDetailRoute(sessionId)) {
                        popUpTo<SessionsRoute> { inclusive = false }
                    }
                },
            )
        }

        composable<ExportRoute> { backStackEntry ->
            val sessionId = backStackEntry.arguments?.getString("sessionId") ?: ""
            val viewModel: ExportViewModel = hiltViewModel()
            ExportScreen(
                viewModel = viewModel,
                sessionId = sessionId,
                onExportComplete = {
                    navController.navigate(SessionsRoute) {
                        popUpTo<SessionsRoute> { inclusive = true }
                    }
                },
            )
        }

        composable<SessionDetailRoute> { backStackEntry ->
            val sessionId = backStackEntry.arguments?.getString("sessionId") ?: ""
            val viewModel: SessionDetailViewModel = hiltViewModel()
            LocalSessionDetailScreen(
                viewModel = viewModel,
                sessionId = sessionId,
                onBack = { navController.popBackStack() },
                onExport = { navController.navigate(ExportRoute(it)) },
            )
        }

        composable<SessionsRoute> {
            val viewModel: SessionListViewModel = hiltViewModel()
            LocalSessionListScreen(
                viewModel = viewModel,
                onSessionClick = { sessionId ->
                    navController.navigate(SessionDetailRoute(sessionId))
                },
                onExportSession = { sessionId ->
                    navController.navigate(ExportRoute(sessionId))
                },
                onNewRecording = {
                    navController.navigate(BleScanRoute) {
                        popUpTo<SessionsRoute> { inclusive = true }
                    }
                },
            )
        }
    }
}
