package ru.skatelab.capture.ui.tabs

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import ru.skatelab.capture.navigation.CameraRoute
import ru.skatelab.capture.navigation.DashboardRoute
import ru.skatelab.capture.navigation.ProfileRoute
import ru.skatelab.capture.navigation.SessionsRoute
import ru.skatelab.capture.ui.camera.CameraScreen
import ru.skatelab.capture.ui.camera.CameraViewModel
import ru.skatelab.capture.ui.dashboard.AndroidDashboardViewModel
import ru.skatelab.capture.ui.dashboard.DashboardScreen
import ru.skatelab.capture.ui.profile.ProfileScreen
import ru.skatelab.capture.ui.profile.ProfileViewModel
import ru.skatelab.capture.ui.session.AndroidSessionsViewModel
import ru.skatelab.capture.ui.session.SessionListScreen

@Composable
fun MainTabsNavHost(
    navController: NavHostController,
    onNavigateToBleScan: () -> Unit,
    onLogout: () -> Unit = {},
    onNavigateToSessionDetail: (String) -> Unit = {},
    onNavigateToMetricTrend: (String, String) -> Unit = { _, _ -> },
    onNavigateToProcessing: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = CameraRoute,
        modifier = modifier,
    ) {
        composable<CameraRoute> {
            val viewModel: CameraViewModel = hiltViewModel()
            CameraScreen(
                viewModel = viewModel,
                onNavigateToImuCapture = onNavigateToBleScan,
                onNavigateToProcessing = onNavigateToProcessing,
            )
        }

        composable<DashboardRoute> {
            val viewModel: AndroidDashboardViewModel = hiltViewModel()
            DashboardScreen(
                viewModel = viewModel,
                onNavigateToSessions = { elementType ->
                    navController.navigate(SessionsRoute)
                },
                onNavigateToSessionDetail = onNavigateToSessionDetail,
            )
        }

        composable<SessionsRoute> {
            val viewModel: AndroidSessionsViewModel = hiltViewModel()
            SessionListScreen(
                viewModel = viewModel,
                onSessionClick = onNavigateToSessionDetail,
                onBack = { navController.popBackStack() },
            )
        }

        composable<ProfileRoute> {
            val viewModel: ProfileViewModel = hiltViewModel()
            ProfileScreen(
                viewModel = viewModel,
                onLogout = onLogout,
            )
        }
    }
}
