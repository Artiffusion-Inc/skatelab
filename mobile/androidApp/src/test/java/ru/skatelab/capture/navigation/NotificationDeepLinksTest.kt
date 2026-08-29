package ru.skatelab.capture.navigation

import org.junit.Assert.assertEquals
import org.junit.Test

class NotificationDeepLinksTest {
    @Test
    fun mapsSupportedNotificationLinksToTypedDestinations() {
        assertEquals(
            NotificationDestination.Session("session-1"),
            mapNotificationDeepLink("skatelab://session/session-1"),
        )
        assertEquals(
            NotificationDestination.TrainingPlan("plan-1"),
            mapNotificationDeepLink("skatelab://training/plan-1"),
        )
        assertEquals(
            NotificationDestination.Export("export-1"),
            mapNotificationDeepLink("skatelab://exports/export-1"),
        )
    }

    @Test
    fun mapsUnknownOrMalformedLinksToSafeFallback() {
        assertEquals(NotificationDestination.Unknown, mapNotificationDeepLink(null))
        assertEquals(
            NotificationDestination.Unknown,
            mapNotificationDeepLink("https://example.com/session/session-1"),
        )
        assertEquals(
            NotificationDestination.Unknown,
            mapNotificationDeepLink("skatelab://session/"),
        )
    }
}
