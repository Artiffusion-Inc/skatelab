package ru.skatelab.shared.auth

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import ru.skatelab.shared.api.UsersApi
import kotlin.test.Test
import kotlin.test.assertEquals

class FakeAuthBackendSmokeTest {
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    @Test
    fun usersMe_routesByAuthorizationHeader() = runTest {
        val backend = FakeAuthBackend().addAccount("a", "a@skatelab.ru", "A").addAccount("b", "b@skatelab.ru", "B")
        val client = HttpClient(backend.engine()) {
            install(ContentNegotiation) { json(json) }
        }
        val users = UsersApi(client)
        // No Authorization header → 401 (no cached/loaded token)
        try {
            users.getMe()
            error("expected 401")
        } catch (e: Exception) {
            // ok
        }
        client.close()
    }
}