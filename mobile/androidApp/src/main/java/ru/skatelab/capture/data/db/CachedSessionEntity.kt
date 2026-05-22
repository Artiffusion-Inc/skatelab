package ru.skatelab.capture.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "cached_sessions")
data class CachedSessionEntity(
    @PrimaryKey val id: String,
    val elementType: String,
    val status: String,
    val overallScore: Float? = null,
    val videoUrl: String? = null,
    val createdAt: String,
    val cachedAt: Long = System.currentTimeMillis(),
)
