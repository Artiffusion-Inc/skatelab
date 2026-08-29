package ru.skatelab.capture.ui.tabs

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import ru.skatelab.capture.R
import ru.skatelab.capture.navigation.CameraRoute
import ru.skatelab.capture.navigation.DashboardRoute
import ru.skatelab.capture.navigation.ProfileRoute
import ru.skatelab.capture.navigation.SessionsRoute

private data class TabItem(
    val labelRes: Int,
    val icon: ImageVector,
    val route: Any,
)

private val TABS =
    listOf(
        TabItem(R.string.tab_camera, Icons.Default.CameraAlt, CameraRoute),
        TabItem(R.string.tab_progress, Icons.Default.Dashboard, DashboardRoute),
        TabItem(R.string.tab_sessions, Icons.Default.History, SessionsRoute),
        TabItem(R.string.tab_profile, Icons.Default.Person, ProfileRoute),
    )

@Composable
fun MainTabsScreen(
    onNavigateToBleScan: () -> Unit,
    onLogout: () -> Unit = {},
    onNavigateToSessionDetail: (String) -> Unit = {},
    onNavigateToMetricTrend: (String, String) -> Unit = { _, _ -> },
    onNavigateToProcessing: (String) -> Unit = {},
    onNavigateToUploadQueue: () -> Unit = {},
    onNavigateToNotifications: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val tabNavController = rememberNavController()
    val backStackEntry by tabNavController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination

    Scaffold(
        modifier = modifier,
        bottomBar = {
            NavigationBar {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = currentDestination?.hasRoute(tab.route::class) == true,
                        onClick = {
                            tabNavController.navigate(tab.route) {
                                popUpTo(tabNavController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = {
                            Icon(
                                tab.icon,
                                contentDescription = stringResource(tab.labelRes),
                            )
                        },
                        label = { Text(stringResource(tab.labelRes)) },
                    )
                }
            }
        },
    ) { innerPadding ->
        MainTabsNavHost(
            navController = tabNavController,
            onNavigateToBleScan = onNavigateToBleScan,
            onLogout = onLogout,
            onNavigateToSessionDetail = onNavigateToSessionDetail,
            onNavigateToMetricTrend = onNavigateToMetricTrend,
            onNavigateToProcessing = onNavigateToProcessing,
            onNavigateToUploadQueue = onNavigateToUploadQueue,
            onNavigateToNotifications = onNavigateToNotifications,
            modifier = Modifier.padding(innerPadding),
        )
    }
}
