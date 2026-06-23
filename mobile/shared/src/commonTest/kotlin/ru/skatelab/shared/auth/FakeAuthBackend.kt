package ru.skatelab.shared.auth

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.respondError
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.http.content.ByteArrayContent
import io.ktor.http.content.OutgoingContent
import io.ktor.http.content.TextContent
import kotlinx.serialization.json.Json

/**
 * Test-only emulation of the SkateLab auth/session backend subset.
 * Routes by `request.url.encodedPath` plus the `Authorization: Bearer <token>` header
 * actually sent, so a stale Ktor Auth-plugin cache surfaces as the wrong account.
 *
 * Mirrors `backend/app/routes/auth.py` refresh semantics: refresh is single-use and
 * rotated — a valid refresh returns a NEW token pair and invalidates the old refresh;
 * an invalid/used refresh returns 401.
 *
 * Tokens are fixed string constants — no Date.now()/Math.random().
 */
class FakeAuthBackend(
    private val json: Json = Json { ignoreUnknownKeys = true; isLenient = true },
) {
    private data class Account(
        val id: String,
        val email: String,
        val displayName: String?,
        val sessions: List<String>, // session ids owned by this account
    )

    private val accounts = mutableMapOf<String, Account>()            // id -> account
    private val accessTokenToAccount = mutableMapOf<String, String>() // accessToken -> accountId
    private val refreshTokenToAccount = mutableMapOf<String, String>() // refreshToken -> accountId
    private val accessAlive = mutableMapOf<String, Boolean>()          // accountId -> access valid
    private val refreshAlive = mutableMapOf<String, Boolean>()         // accountId -> refresh valid
    private val usedRefreshTokens = mutableSetOf<String>()             // rotated-away (single-use)
    private var refreshCallCount = 0

    // Per-account fixed token prefixes; rotated refresh appends a counter.
    private val tokenCounter = mutableMapOf<String, Int>()            // accountId -> rotation counter

    fun addAccount(id: String, email: String, displayName: String? = null): FakeAuthBackend {
        accounts[id] = Account(id, email, displayName, listOf("${id}-sess-1"))
        accessAlive[id] = true
        refreshAlive[id] = true
        tokenCounter[id] = 0
        return this
    }

    fun expireAccessToken(accountId: String) { accessAlive[accountId] = false }
    fun revokeRefreshToken(accountId: String) {
        refreshAlive[accountId] = false
        // Mark ALL currently-issued refresh tokens for this account as used so they
        // can never refresh again, even after a re-login re-enables refresh issuance.
        val toRevoke = refreshTokenToAccount.filterValues { it == accountId }.keys.toList()
        toRevoke.forEach { tok ->
            usedRefreshTokens.add(tok)
            refreshTokenToAccount.remove(tok)
        }
    }

    /** Number of refresh-endpoint calls that presented a refresh token (successful or
     *  rejected; does not count malformed/empty-body attempts). */
    fun refreshCallCount(): Int = refreshCallCount

    private fun jsonHeaders() =
        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    private fun issueTokensFor(accountId: String): Pair<String, String> {
        val n = (tokenCounter[accountId] ?: 0) + 1
        tokenCounter[accountId] = n
        val access = "acc-$accountId-$n"
        val refresh = "ref-$accountId-$n"
        accessTokenToAccount[access] = accountId
        refreshTokenToAccount[refresh] = accountId
        accessAlive[accountId] = true
        refreshAlive[accountId] = true
        return access to refresh
    }

    private fun accountForAccessToken(authHeader: String?): Account? {
        val token = authHeader?.removePrefix("Bearer ")?.trim() ?: return null
        val accountId = accessTokenToAccount[token] ?: return null
        return accounts[accountId]
    }

    private fun profileJson(acc: Account): String =
        """{"id":"${acc.id}","email":"${acc.email}","display_name":${acc.displayName?.let { "\"$it\"" } ?: "null"}}"""

    private fun sessionsListJson(acc: Account): String {
        val items = acc.sessions.joinToString(",") { sid ->
            """{"id":"$sid","user_id":"${acc.id}","element_type":"flip","status":"completed","created_at":"2026-05-24T12:00:00Z"}"""
        }
        return """{"sessions":[$items],"total":${acc.sessions.size},"next_cursor":null,"has_more":false}"""
    }

    private fun sessionJson(acc: Account, sid: String): String =
        """{"id":"$sid","user_id":"${acc.id}","element_type":"flip","status":"completed","created_at":"2026-05-24T12:00:00Z"}"""

    fun engine(): MockEngine = MockEngine { request ->
        val path = request.url.encodedPath
        val authHeader = request.headers[HttpHeaders.Authorization]
        val body = bodyText(request.body)

        when {
            path.endsWith("auth/login") -> {
                val email = extractEmail(body) ?: error("login body missing email")
                val accountId = accounts.values.firstOrNull { it.email == email }?.id
                    ?: error("no account registered for email $email")
                val (access, refresh) = issueTokensFor(accountId)
                respond(
                    """{"access_token":"$access","refresh_token":"$refresh","token_type":"bearer"}""",
                    status = HttpStatusCode.OK,
                    headers = jsonHeaders(),
                )
            }

            path.endsWith("auth/logout") -> respond("{}", status = HttpStatusCode.OK, headers = jsonHeaders())

            path.endsWith("auth/refresh") -> {
                val refreshIn = extractRefreshToken(body) ?: return@MockEngine respondError(
                    HttpStatusCode.Unauthorized, """{"detail":"Refresh token required"}""",
                )
                refreshCallCount += 1
                val accountId = refreshTokenToAccount[refreshIn]
                when {
                    accountId == null || refreshAlive[accountId] != true ->
                        respondError(HttpStatusCode.Unauthorized, """{"detail":"Invalid or expired refresh token"}""")
                    usedRefreshTokens.contains(refreshIn) ->
                        respondError(HttpStatusCode.Unauthorized, """{"detail":"Token reuse detected. All sessions revoked."}""")
                    else -> {
                        usedRefreshTokens.add(refreshIn)
                        val (newAccess, newRefresh) = issueTokensFor(accountId)
                        respond(
                            """{"access_token":"$newAccess","refresh_token":"$newRefresh","token_type":"bearer"}""",
                            status = HttpStatusCode.OK,
                            headers = jsonHeaders(),
                        )
                    }
                }
            }

            path.endsWith("users/me") -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    respond(profileJson(acc), status = HttpStatusCode.OK, headers = jsonHeaders())
                }
            }

            // Settings endpoint is only exercised for auth gating in this suite;
            // deliberately returns the profile body (suite doesn't deserialize settings fields).
            path.endsWith("users/me/settings") -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    respond(profileJson(acc), status = HttpStatusCode.OK, headers = jsonHeaders())
                }
            }

            path.endsWith("sessions") && request.method.value == "GET" -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    respond(sessionsListJson(acc), status = HttpStatusCode.OK, headers = jsonHeaders())
                }
            }

            path.startsWith("/v1/sessions/") && request.method.value == "GET" -> {
                val acc = accountForAccessToken(authHeader)
                if (acc == null || accessAlive[acc.id] != true) {
                    respondError(HttpStatusCode.Unauthorized, """{"detail":"Unauthorized"}""")
                } else {
                    val sid = path.removePrefix("/v1/sessions/").removeSuffix("/")
                    if (acc.sessions.contains(sid)) {
                        respond(sessionJson(acc, sid), status = HttpStatusCode.OK, headers = jsonHeaders())
                    } else {
                        respondError(HttpStatusCode.NotFound, """{"detail":"Not Found"}""")
                    }
                }
            }

            else -> respondError(HttpStatusCode.NotFound, """{"detail":"Not Found"}""")
        }
    }

    private fun extractRefreshToken(body: String): String? {
        val match = """"refresh_token"\s*:\s*"([^"]+)"""".toRegex().find(body)
        return match?.groupValues?.get(1)
    }

    private fun extractEmail(body: String): String? {
        val match = """"email"\s*:\s*"([^"]+)"""".toRegex().find(body)
        return match?.groupValues?.get(1)
    }

    private fun bodyText(content: OutgoingContent): String = when (content) {
        is TextContent -> content.text
        is ByteArrayContent -> content.bytes().decodeToString()
        else -> ""
    }
}