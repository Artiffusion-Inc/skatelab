package ru.skatelab.capture.ui.tabs

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import ru.skatelab.capture.navigation.BleScanRoute
import ru.skatelab.capture.navigation.CameraRoute
import ru.skatelab.capture.navigation.MoreRoute
import ru.skatelab.capture.navigation.ProfileRoute
import ru.skatelab.capture.navigation.ResultsRoute
import ru.skatelab.capture.ui.camera.CameraScreen
import ru.skatelab.capture.ui.camera.CameraViewModel
import ru.skatelab.capture.ui.profile.MoreScreen
import ru.skatelab.capture.ui.profile.ProfileScreen
import ru.skatelab.capture.ui.profile.ProfileViewModel

@Composable
fun MainTabsNavHost(
    navController: NavHostController,
    onNavigateToBleScan: () -> Unit,
    onLogout: () -> Unit = {},
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
            )
        }

        composable<ResultsRoute> {
            ResultsPlaceholder()
        }

        composable<ProfileRoute> {
            val viewModel: ProfileViewModel = hiltViewModel()
            ProfileScreen(
                viewModel = viewModel,
                onLogout = onLogout,
            )
        }

        composable<MoreRoute> {
            val viewModel: ProfileViewModel = hiltViewModel()
            MoreScreen(
                viewModel = viewModel,
                onNavigateToBleScan = onNavigateToBleScan,
                onLogout = onLogout,
            )
        }
    }
}

@Composable
private fun ResultsPlaceholder() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            "Results — coming soon",
            style = MaterialTheme.typography.headlineSmall,
        )
    }
}