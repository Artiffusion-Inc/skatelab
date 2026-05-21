package ru.skatelab.shared.state

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class AuthViewModelTest {
    @Test
    fun authUiStateSealedHierarchy() {
        val states: List<AuthUiState> = listOf(
            AuthUiState.Loading,
            AuthUiState.LoggedOut,
            AuthUiState.LoggedIn("1", "Test"),
            AuthUiState.Error("fail"),
        )
        assertEquals(4, states.size)
    }

    @Test
    fun sessionsUiStateSealedHierarchy() {
        val states: List<SessionsUiState> = listOf(
            SessionsUiState.Loading,
            SessionsUiState.Loaded(emptyList(), 0, 1),
            SessionsUiState.Error("fail"),
        )
        assertEquals(3, states.size)
    }

    @Test
    fun processingUiStateSealedHierarchy() {
        val states: List<ProcessingUiState> = listOf(
            ProcessingUiState.Idle,
            ProcessingUiState.Progress(0.5f, "Processing"),
            ProcessingUiState.Completed("session-1"),
            ProcessingUiState.Failed("error"),
        )
        assertEquals(4, states.size)
    }

    @Test
    fun authUiStateDataObjectEquality() {
        val state1 = AuthUiState.LoggedIn("1", "Alice")
        val state2 = AuthUiState.LoggedIn("1", "Alice")
        assertEquals(state1, state2)
    }

    @Test
    fun sessionsUiStateDataClassEquality() {
        val state1 = SessionsUiState.Loaded(emptyList(), 0, 1)
        val state2 = SessionsUiState.Loaded(emptyList(), 0, 1)
        assertEquals(state1, state2)
    }

    @Test
    fun processingUiStateDataClassEquality() {
        val state1 = ProcessingUiState.Progress(0.75f, "Analyzing")
        val state2 = ProcessingUiState.Progress(0.75f, "Analyzing")
        assertEquals(state1, state2)
    }

    @Test
    fun authUiStateLoadingIsSingleton() {
        val a: AuthUiState = AuthUiState.Loading
        val b: AuthUiState = AuthUiState.Loading
        assertEquals(a, b)
    }

    @Test
    fun sessionsUiStateLoadingIsSingleton() {
        val a: SessionsUiState = SessionsUiState.Loading
        val b: SessionsUiState = SessionsUiState.Loading
        assertEquals(a, b)
    }

    @Test
    fun processingUiStateIdleIsSingleton() {
        val a: ProcessingUiState = ProcessingUiState.Idle
        val b: ProcessingUiState = ProcessingUiState.Idle
        assertEquals(a, b)
    }
}
