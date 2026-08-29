package ru.skatelab.shared.api

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import ru.skatelab.shared.models.ConnectionListResponse
import ru.skatelab.shared.models.ConnectionResponse
import ru.skatelab.shared.models.InviteRequest
import ru.skatelab.shared.utils.expectSuccess

class ConnectionsApi(private val client: HttpClient) {
    suspend fun list(): ConnectionListResponse =
        client.get("connections").expectSuccess().body()

    suspend fun pending(): ConnectionListResponse =
        client.get("connections/pending").expectSuccess().body()

    suspend fun invite(request: InviteRequest): ConnectionResponse =
        client.post("connections/invite") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.expectSuccess().body()

    suspend fun accept(connectionId: String): ConnectionResponse =
        client.post("connections/$connectionId/accept").expectSuccess().body()

    suspend fun end(connectionId: String): ConnectionResponse =
        client.post("connections/$connectionId/end").expectSuccess().body()
}
