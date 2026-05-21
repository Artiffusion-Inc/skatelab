# OOFSkate Mobile Clone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a KMP mobile app (Android-first, iOS-ready) that clones OOFSkate functionality: video recording → server-side ML analysis → biomechanical metrics display on device.

**Architecture:** KMP shared module (Ktor, models, auth, state) + native Android UI (Compose). Server-side GPU processing via existing backend. Optional BLE IMU (Kable) for enhanced accuracy. WorkManager + Room for offline-first upload.

**Tech Stack:** Kotlin 2.1.21, KMP, Ktor 3.1.3, Compose (BOM 2025.05.01), Hilt 2.56.1, CameraX 1.5.3, Media3 1.6.0, Vico 2.1.0, Kable (BLE), Mokkery (commonTest), Room, WorkManager, kotlinx.serialization

**Parallel Tracks:** A (Backend/ML), B (KMP Shared), C (Android App) — zero file overlap between tracks.

---

## File Structure

### New files (KMP shared module)

```
mobile/
├── build-logic/
│   └── convention/
│       ├── build.gradle.kts
│       └── src/main/kotlin/
│           ├── kmp-library-convention.gradle.kts
│           ├── android-app-convention.gradle.kts
│           ├── compose-convention.gradle.kts
│           └── serialization-convention.gradle.kts
├── shared/
│   ├── build.gradle.kts
│   └── src/
│       ├── commonMain/kotlin/ru/skatelab/shared/
│       │   ├── api/
│       │   │   ├── SkateLabClient.kt          # Ktor HTTP client
│       │   │   ├── AuthApi.kt                 # Login, register, refresh
│       │   │   ├── SessionsApi.kt             # CRUD + list
│       │   │   ├── UsersApi.kt                # Profile + settings
│       │   │   ├── UploadsApi.kt              # Init/complete multipart
│       │   │   └── ProcessApi.kt              # Queue + SSE stream
│       │   ├── models/
│       │   │   ├── TokenResponse.kt
│       │   │   ├── UserResponse.kt
│       │   │   ├── SessionResponse.kt
│       │   │   ├── SessionListResponse.kt
│       │   │   ├── SessionMetricResponse.kt
│       │   │   ├── UploadInitResponse.kt
│       │   │   └── ProcessEvent.kt
│       │   ├── auth/
│       │   │   ├── AuthRepository.kt
│       │   │   ├── TokenStorage.kt            # expect/actual
│       │   │   └── AuthInterceptor.kt         # Ktor interceptor for refresh
│       │   ├── state/
│       │   │   ├── AuthViewModel.kt
│       │   │   ├── SessionsViewModel.kt
│       │   │   └── ProcessingViewModel.kt
│       │   └── util/
│       │       ├── DateTimeExt.kt
│       │       └── ResultExt.kt
│       ├── commonTest/kotlin/ru/skatelab/shared/
│       │   ├── api/
│       │   ├── models/
│       │   ├── auth/
│       │   └── state/
│       ├── androidMain/kotlin/ru/skatelab/shared/
│       │   ├── auth/
│       │   │   └── AndroidTokenStorage.kt     # EncryptedSharedPreferences
│       │   └── platform/
│       │       └── ClockNanos.kt
│       └── iosMain/kotlin/ru/skatelab/shared/  # (later)
├── androidApp/
│   ├── build.gradle.kts
│   └── src/main/java/ru/skatelab/capture/
│       ├── App.kt
│       ├── MainActivity.kt
│       ├── navigation/
│       │   ├── AppNavigation.kt
│       │   └── Routes.kt
│       ├── ui/
│       │   ├── auth/
│       │   │   ├── LoginScreen.kt
│       │   │   ├── RegisterScreen.kt
│       │   │   └── SplashScreen.kt
│       │   ├── camera/
│       │   │   └── CameraScreen.kt
│       │   ├── session/
│       │   │   ├── SessionListScreen.kt
│       │   │   ├── SessionDetailScreen.kt
│       │   │   └── MetricCard.kt
│       │   ├── processing/
│       │   │   └── ProcessingScreen.kt
│       │   ├── profile/
│       │   │   └── ProfileScreen.kt
│       │   ├── skeleton/
│       │   │   └── SkeletonOverlay.kt
│       │   └── tabs/
│       │       └── MainTabs.kt
│       ├── upload/
│       │   ├── UploadWorker.kt
│       │   └── ChunkedUploader.kt
│       ├── data/
│       │   ├── db/
│       │   │   ├── AppDatabase.kt
│       │   │   ├── PendingUploadEntity.kt
│       │   │   └── CachedSessionEntity.kt
│       │   ├── ble/  (migrated from existing)
│       │   ├── camera/  (migrated from existing)
│       │   └── export/  (migrated from existing)
│       └── di/
│           ├── AppModule.kt
│           ├── NetworkModule.kt
│           └── DatabaseModule.kt
└── gradle/
    └── libs.versions.toml
```

### Modified files (backend/ML)

```
backend/app/models/user.py           # Add angular_unit_preference column
backend/app/schemas.py               # Add angular_unit to UpdateSettingsRequest
backend/app/routes/users.py          # Add POST /me/avatar endpoint
backend/app/routes/uploads.py        # Add POST /presign for small files
backend/alembic/versions/xxx_add_angular_unit.py  # Migration

ml/src/analysis/metrics.py           # Add compute_total_rotation, compute_under_rotation
ml/src/analysis/element_defs.py      # Add spin type definitions
ml/src/tas/classifier.py             # Train and export SegmentClassifier
ml/gpu_server/server.py              # Load new classifier models
```

---

## WAVE 1: Foundation (Week 1, Days 1-2)

All tracks start in parallel. Track B is on the critical path.

---

### Task 1: KMP Gradle Scaffolding [Track B]

**Files:**

- Create: `mobile/gradle/libs.versions.toml`
- Create: `mobile/build-logic/convention/build.gradle.kts`
- Create: `mobile/build-logic/convention/src/main/kotlin/kmp-library-convention.gradle.kts`
- Create: `mobile/build-logic/convention/src/main/kotlin/android-app-convention.gradle.kts`
- Create: `mobile/build-logic/convention/src/main/kotlin/compose-convention.gradle.kts`
- Create: `mobile/build-logic/convention/src/main/kotlin/serialization-convention.gradle.kts`
- Modify: `mobile/settings.gradle.kts`
- Modify: `mobile/build.gradle.kts`

- [ ] **Step 1: Create version catalog**

```toml
# mobile/gradle/libs.versions.toml
[versions]
kotlin = "2.1.21"
agp = "8.9.1"
compose-bom = "2025.05.01"
ktor = "3.1.3"
serialization = "1.8.1"
coroutines = "1.10.2"
hilt = "2.56.1"
camerax = "1.5.3"
media3 = "1.6.0"
vico = "2.1.0"
room = "2.7.1"
work = "2.10.1"
kable = "2.3.1"
mokkery = "2.7.0"
kover = "0.9.1"
navigation = "2.9.0"
lifecycle = "2.9.0"
ktlint = "12.2.0"

[libraries]
# KMP shared
ktor-client-core = { module = "io.ktor:ktor-client-core", version.ref = "ktor" }
ktor-client-okhttp = { module = "io.ktor:ktor-client-okhttp", version.ref = "ktor" }
ktor-client-content-negotiation = { module = "io.ktor:ktor-client-content-negotiation", version.ref = "ktor" }
ktor-serialization-json = { module = "io.ktor:ktor-serialization-kotlinx-json", version.ref = "ktor" }
ktor-client-auth = { module = "io.ktor:ktor-client-auth", version.ref = "ktor" }
kotlinx-serialization-json = { module = "org.jetbrains.kotlinx:kotlinx-serialization-json", version.ref = "serialization" }
kotlinx-coroutines-core = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-core", version.ref = "coroutines" }
kotlinx-datetime = { module = "org.jetbrains.kotlinx:kotlinx-datetime", version = "0.6.2" }
kotlinx-coroutines-test = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-test", version.ref = "coroutines" }
kotlin-test = { module = "org.jetbrains.kotlin:kotlin-test", version.ref = "kotlin" }

# Android
compose-bom = { module = "androidx.compose:compose-bom", version.ref = "compose-bom" }
hilt-android = { module = "com.google.dagger:hilt-android", version.ref = "hilt" }
hilt-compiler = { module = "com.google.dagger:hilt-android-compiler", version.ref = "hilt" }
navigation-compose = { module = "androidx.navigation:navigation-compose", version.ref = "navigation" }
lifecycle-viewmodel-compose = { module = "androidx.lifecycle:lifecycle-viewmodel-compose", version.ref = "lifecycle" }
camerax-core = { module = "androidx.camera:camera-core", version.ref = "camerax" }
camerax-camera2 = { module = "androidx.camera:camera-camera2", version.ref = "camerax" }
camerax-lifecycle = { module = "androidx.camera:camera-lifecycle", version.ref = "camerax" }
camerax-video = { module = "androidx.camera:camera-video", version.ref = "camerax" }
media3-exoplayer = { module = "androidx.media3:media3-exoplayer", version.ref = "media3" }
media3-ui = { module = "androidx.media3:media3-ui", version.ref = "media3" }
vico-compose = { module = "com.patrykandpatrick.vico:compose", version.ref = "vico" }
vico-compose-m3 = { module = "com.patrykandpatrick.vico:compose-m3", version.ref = "vico" }
room-runtime = { module = "androidx.room:room-runtime", version.ref = "room" }
room-ktx = { module = "androidx.room:room-ktx", version.ref = "room" }
room-compiler = { module = "androidx.room:room-compiler", version.ref = "room" }
work-runtime-ktx = { module = "androidx.work:work-runtime-ktx", version.ref = "work" }
hilt-work = { module = "androidx.hilt:hilt-work", version = "1.2.0" }
security-crypto = { module = "androidx.security:security-crypto", version = "1.1.0-alpha06" }
activity-compose = { module = "androidx.activity:activity-compose", version = "1.10.1" }
core-ktx = { module = "androidx.core:core-ktx", version = "1.16.0" }

# Testing
junit = { module = "junit:junit", version = "4.13.2" }
mockk = { module = "io.mockk:mockk", version = "1.14.0" }
turbine = { module = "app.cash.turbine:turbine", version = "1.2.0" }
mokkery = { module = "dev.mokkery:dev.mokkery.gradle.plugin", version.ref = "mokkery" }

[plugins]
kmp-library = { id = "org.jetbrains.kotlin.multiplatform", version.ref = "kotlin" }
android-application = { id = "com.android.application", version.ref = "agp" }
android-library = { id = "com.android.library", version.ref = "agp" }
serialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
compose-compiler = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
hilt = { id = "com.google.dagger.hilt.android", version.ref = "hilt" }
ksp = { id = "com.google.devtools.ksp", version.ref = "kotlin" }
kover = { id = "org.jetbrains.kotlinx.kover", version.ref = "kover" }
ktlint = { id = "org.jlleitschuh.gradle.ktlint", version.ref = "ktlint" }
mokkery-plugin = { id = "dev.mokkery", version.ref = "mokkery" }
```

- [ ] **Step 2: Create convention plugins**

```kotlin
// mobile/build-logic/convention/build.gradle.kts
plugins {
    `kotlin-dsl`
}

dependencies {
    compileOnly(libs.kotlin.gradlePlugin)
    compileOnly(libs.android.gradlePlugin)
    compileOnly(libs.compose.compiler.gradlePlugin)
}

// Use version catalog in convention plugins
val libs = extensions.getByType<VersionCatalogsExtension>().named("libs")
```

```kotlin
// mobile/build-logic/convention/src/main/kotlin/kmp-library-convention.gradle.kts
plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("dev.mokkery")
}

kotlin {
    androidTarget { compilations.all { kotlinOptions.jvmTarget = "17" } }
    iosArm64()
    iosSimulatorArm64()

    sourceSets {
        commonMain.dependencies {
            implementation(libs.kotlinx.coroutines.core)
            implementation(libs.kotlinx.serialization.json)
            implementation(libs.kotlinx.datetime)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
            implementation(libs.kotlinx.coroutines.test)
        }
    }
}

android {
    compileSdk = 35
    minSdk = 24
    namespace = "ru.skatelab.shared"
}
```

```kotlin
// mobile/build-logic/convention/src/main/kotlin/android-app-convention.gradle.kts
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.dagger.hilt.android")
    id("com.google.devtools.ksp")
    id("org.jlleitschuh.gradle.ktlint")
}

android {
    compileSdk = 35
    defaultConfig { minSdk = 24; targetSdk = 35 }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
```

```kotlin
// mobile/build-logic/convention/src/main/kotlin/compose-convention.gradle.kts
plugins {
    id("org.jetbrains.kotlin.plugin.compose")
}

dependencies {
    val composeBom = platform(libs.compose.bom)
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
```

```kotlin
// mobile/build-logic/convention/src/main/kotlin/serialization-convention.gradle.kts
plugins {
    id("org.jetbrains.kotlin.plugin.serialization")
}

dependencies {
    implementation(libs.kotlinx.serialization.json)
}
```

- [ ] **Step 3: Update settings.gradle.kts**

```kotlin
// mobile/settings.gradle.kts
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "skatelab-mobile"
include(":shared")
include(":androidApp")
includeBuild("build-logic")
```

- [ ] **Step 4: Update root build.gradle.kts**

```kotlin
// mobile/build.gradle.kts
plugins {
    alias(libs.plugins.kmp.library) apply false
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.compose.compiler) apply false
    alias(libs.plugins.hilt) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.kover) apply false
    alias(libs.plugins.ktlint) apply false
    alias(libs.plugins.mokkery.plugin) apply false
}
```

- [ ] **Step 5: Create shared module build.gradle.kts**

```kotlin
// mobile/shared/build.gradle.kts
plugins {
    id("kmp-library-convention")
    id("serialization-convention")
    alias(libs.plugins.kmp.library)
    alias(libs.plugins.kover)
}

kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(libs.ktor.client.core)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.json)
            implementation(libs.ktor.client.auth)
        }
        androidMain.dependencies {
            implementation(libs.ktor.client.okhttp)
        }
        iosMain.dependencies {
            implementation("io.ktor:ktor-client-darwin:${libs.versions.ktor.get()}")
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
            implementation(libs.kotlinx.coroutines.test)
        }
    }
}
```

- [ ] **Step 6: Verify build compiles**

Run: `cd mobile && ./gradlew :shared:build`
Expected: BUILD SUCCESSFUL (empty module compiles)

- [ ] **Step 7: Commit**

```bash
git add mobile/gradle/ mobile/build-logic/ mobile/shared/ mobile/settings.gradle.kts mobile/build.gradle.kts
git commit -m "chore(mobile): add KMP shared module scaffolding with convention plugins"
```

---

### Task 2: Shared Models [Track B]

**Files:**

- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/TokenResponse.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/UserResponse.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionResponse.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionListResponse.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionMetricResponse.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/UploadInitResponse.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/ProcessEvent.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/SerializationTest.kt`

These models mirror `backend/app/schemas.py` responses.

- [ ] **Step 1: Write serialization test**

```kotlin
// mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/models/SerializationTest.kt
package ru.skatelab.shared.models

import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import kotlin.test.Test
import kotlin.test.assertEquals

class SerializationTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun tokenResponseRoundtrip() {
        val original = TokenResponse(
            accessToken = "abc123",
            refreshToken = "def456",
            tokenType = "bearer",
        )
        val encoded = json.encodeToString(original)
        val decoded = json.decodeFromString<TokenResponse>(encoded)
        assertEquals(original, decoded)
    }

    @Test
    fun sessionMetricResponseDeserialize() {
        val payload = """{"id":"m1","metric_name":"jump_height","metric_value":45.2,"is_pr":false,"prev_best":null,"reference_value":50.0,"is_in_range":true}"""
        val decoded = json.decodeFromString<SessionMetricResponse>(payload)
        assertEquals("jump_height", decoded.metricName)
        assertEquals(45.2, decoded.metricValue)
    }

    @Test
    fun processEventDeserialize() {
        val payload = """{"progress":0.7,"message":"GPU processing complete","status":"running"}"""
        val decoded = json.decodeFromString<ProcessEvent>(payload)
        assertEquals(0.7f, decoded.progress)
        assertEquals(ProcessStatus.RUNNING, decoded.status)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :shared:jvmTest`
Expected: FAIL — classes not defined

- [ ] **Step 3: Implement models**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/TokenResponse.kt
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
)
```

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/UserResponse.kt
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UserResponse(
    val id: String,
    val email: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    val bio: String? = null,
    @SerialName("height_cm") val heightCm: Float? = null,
    @SerialName("weight_kg") val weightKg: Float? = null,
    val language: String = "ru",
    val timezone: String = "UTC",
    val theme: String = "dark",
    @SerialName("onboarding_role") val onboardingRole: String? = null,
    @SerialName("angular_unit") val angularUnit: String = "deg_per_sec",
)
```

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionResponse.kt
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionResponse(
    val id: String,
    @SerialName("user_id") val userId: String,
    @SerialName("element_type") val elementType: String,
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("processed_video_url") val processedVideoUrl: String? = null,
    val status: String,
    @SerialName("overall_score") val overallScore: Float? = null,
    val recommendations: List<String>? = null,
    val metrics: List<SessionMetricResponse> = emptyList(),
    @SerialName("created_at") val createdAt: String,
)
```

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionListResponse.kt
package ru.skatelab.shared.models

import kotlinx.serialization.Serializable

@Serializable
data class SessionListResponse(
    val sessions: List<SessionResponse>,
    val total: Int,
    val page: Int,
    @SerialName("page_size") val pageSize: Int,
    val pages: Int,
)
```

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/SessionMetricResponse.kt
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionMetricResponse(
    val id: String,
    @SerialName("metric_name") val metricName: String,
    @SerialName("metric_value") val metricValue: Float,
    @SerialName("is_pr") val isPr: Boolean,
    @SerialName("prev_best") val prevBest: Float? = null,
    @SerialName("reference_value") val referenceValue: Float? = null,
    @SerialName("is_in_range") val isInRange: Boolean? = null,
)
```

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/UploadInitResponse.kt
package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UploadInitResponse(
    @SerialName("upload_id") val uploadId: String,
    val key: String,
    @SerialName("chunk_size") val chunkSize: Int,
    @SerialName("part_count") val partCount: Int,
    val parts: List<UploadPart>,
)

@Serializable
data class UploadPart(
    @SerialName("part_number") val partNumber: Int,
    val url: String,
)

@Serializable
data class UploadCompleteRequest(
    @SerialName("upload_id") val uploadId: String,
    val key: String,
    val parts: List<CompletedPart>,
)

@Serializable
data class CompletedPart(
    @SerialName("part_number") val partNumber: Int,
    val etag: String,
)
```

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/ProcessEvent.kt
package ru.skatelab.shared.models

import kotlinx.serialization.Serializable

enum class ProcessStatus {
    RUNNING, COMPLETED, FAILED, CANCELLED,
    @Suppress("unused") UNKNOWN,
}

@Serializable
data class ProcessEvent(
    val progress: Float = 0f,
    val message: String = "",
    val status: String = "running",
) {
    val parsedStatus: ProcessStatus
        get() = when (status) {
            "running" -> ProcessStatus.RUNNING
            "completed" -> ProcessStatus.COMPLETED
            "failed" -> ProcessStatus.FAILED
            "cancelled" -> ProcessStatus.CANCELLED
            else -> ProcessStatus.UNKNOWN
        }
}
```

- [ ] **Step 4: Run tests**

Run: `cd mobile && ./gradlew :shared:jvmTest`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/src/
git commit -m "feat(mobile/shared): add API response models with serialization tests"
```

---

### Task 3: Backend — angular_unit_preference [Track A]

**Files:**

- Modify: `backend/app/models/user.py` — add `angular_unit` column
- Modify: `backend/app/schemas.py` — add `angular_unit` to `UpdateSettingsRequest`
- Modify: `backend/app/routes/users.py` — pass `angular_unit` to update
- Create: `backend/alembic/versions/xxx_add_angular_unit_preference.py`
- Test: `backend/tests/test_users.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_users.py (append to existing or create)
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_update_angular_unit(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        "/me/settings",
        json={"angular_unit": "rpm"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["angular_unit"] == "rpm"

    # Verify persists
    resp2 = await client.get("/me", headers=auth_headers)
    assert resp2.json()["angular_unit"] == "rpm"
```

- [ ] **Step 2: Run test**

Run: `cd backend && uv run pytest tests/test_users.py::test_update_angular_unit -v`
Expected: FAIL — `angular_unit` not in model

- [ ] **Step 3: Add angular_unit to User model**

Add to `backend/app/models/user.py` in the User class:
```python
angular_unit: Mapped[str] = mapped_column(String(20), server_default="deg_per_sec", nullable=False)
```

- [ ] **Step 4: Add to UpdateSettingsRequest schema**

In `backend/app/schemas.py`, add field to `UpdateSettingsRequest`:
```python
angular_unit: str | None = None
```

Add to `UserResponse`:
```python
angular_unit: str = "deg_per_sec"
```

- [ ] **Step 5: Add to users.py update call**

In `backend/app/routes/users.py`, update `update_settings` to pass `angular_unit`:
```python
angular_unit=data.angular_unit,
```

- [ ] **Step 6: Create Alembic migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "add angular_unit_preference"`
Run: `cd backend && uv run alembic upgrade head`

- [ ] **Step 7: Run test**

Run: `cd backend && uv run pytest tests/test_users.py::test_update_angular_unit -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/user.py backend/app/schemas.py backend/app/routes/users.py backend/alembic/ backend/tests/test_users.py
git commit -m "feat(backend): add angular_unit_preference to user settings"
```

---

### Task 4: Backend — Avatar Upload [Track A]

**Files:**

- Modify: `backend/app/routes/users.py` — add `POST /me/avatar` endpoint
- Modify: `backend/app/schemas.py` — add `AvatarUploadResponse`
- Modify: `backend/app/models/user.py` — ensure `avatar_url` writable
- Test: `backend/tests/test_users.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_upload_avatar(client: AsyncClient, auth_headers: dict, mock_r2):
    import io
    img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    resp = await client.post(
        "/me/avatar",
        files={"file": ("avatar.png", img, "image/png")},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "avatar_url" in resp.json()
```

- [ ] **Step 2: Implement endpoint**

Add to `backend/app/routes/users.py`:
```python
@post("/avatar")
async def upload_avatar(
    self,
    user: CurrentUser,
    db: DbDep,
    file: UploadFile = Parameter(content_type=["image/png", "image/jpeg", "image/webp"]),
) -> UserResponse:
    key = f"avatars/{user.id}/{file.filename}"
    url = await upload_to_r2(key, await file.read(), content_type=file.content_type)
    updated = await update(db, user, avatar_url=url)
    return UserResponse.model_validate(updated)
```

- [ ] **Step 3: Run test**

Run: `cd backend && uv run pytest tests/test_users.py::test_upload_avatar -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/users.py backend/tests/test_users.py
git commit -m "feat(backend): add POST /me/avatar endpoint for profile pictures"
```

---

### Task 5: Android App Scaffold [Track C]

**Files:**

- Create: `mobile/androidApp/build.gradle.kts`
- Move: All files from `mobile/app/src/main/java/ru/skatelab/capture/` to `mobile/androidApp/src/main/java/ru/skatelab/capture/`
- Move: `mobile/app/src/main/proto/` to `mobile/androidApp/src/main/proto/`
- Move: `mobile/app/src/test/` to `mobile/androidApp/src/test/`
- Move: `mobile/app/src/androidTest/` to `mobile/androidApp/src/androidTest/`
- Delete: `mobile/app/` directory after migration

- [ ] **Step 1: Create androidApp build.gradle.kts**

```kotlin
// mobile/androidApp/build.gradle.kts
plugins {
    id("android-app-convention")
    id("compose-convention")
    id("serialization-convention")
    alias(libs.plugins.android.application)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
    alias(libs.plugins.kover)
}

android {
    namespace = "ru.skatelab.capture"
    defaultConfig {
        applicationId = "ru.skatelab.capture"
        versionCode = 1
        versionName = "1.0.0"
        targetSdk = 35
    }
}

dependencies {
    implementation(project(":shared"))

    implementation(libs.core.ktx)
    implementation(libs.activity.compose)
    implementation(libs.navigation.compose)
    implementation(libs.lifecycle.viewmodel.compose)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.work)

    implementation(libs.camerax.core)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.video)

    implementation(libs.media3.exoplayer)
    implementation(libs.media3.ui)

    implementation(libs.vico.compose)
    implementation(libs.vico.compose.m3)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    implementation(libs.work.runtime.ktx)
    implementation(libs.security.crypto)

    testImplementation(libs.junit)
    testImplementation(libs.mockk)
    testImplementation(libs.turbine)
}

kover {
    reports {
        filters {
            includes {
                packages("ru.skatelab.capture.*")
            }
        }
    }
}
```

- [ ] **Step 2: Copy existing source files to androidApp**

```bash
mkdir -p mobile/androidApp/src/main/java
cp -r mobile/app/src/main/java/ru mobile/androidApp/src/main/java/
cp -r mobile/app/src/main/proto mobile/androidApp/src/main/
cp -r mobile/app/src/test mobile/androidApp/src/
cp -r mobile/app/src/androidTest mobile/androidApp/src/
cp mobile/app/src/main/AndroidManifest.xml mobile/androidApp/src/main/
cp -r mobile/app/src/main/res mobile/androidApp/src/main/
```

- [ ] **Step 3: Update settings.gradle.kts**

Already done in Task 1 — `include(":androidApp")` is there.

- [ ] **Step 4: Verify build**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Remove old :app module**

Delete `mobile/app/` directory. Update `settings.gradle.kts` to remove `include(":app")` if it was there (already replaced with `:androidApp`).

- [ ] **Step 6: Verify build again**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 7: Commit**

```bash
git add mobile/androidApp/ mobile/settings.gradle.kts
git rm -r mobile/app/
git commit -m "refactor(mobile): migrate :app to :androidApp module for KMP structure"
```

---

### Task 6: ML — Under-rotation [Track D]

**Files:**

- Modify: `ml/src/analysis/metrics.py` — add `compute_total_rotation()` and `compute_under_rotation()`
- Modify: `ml/src/analysis/element_defs.py` — ensure `ElementDef.rotations` covers multi-rotation jumps
- Test: `ml/tests/analysis/test_under_rotation.py`

- [ ] **Step 1: Write failing tests**

```python
# ml/tests/analysis/test_under_rotation.py
import numpy as np
import pytest

def test_total_rotation_single():
    """One full rotation = 360 degrees."""
    from ml.src.analysis.metrics import compute_total_rotation
    angles = np.linspace(0, 2 * np.pi, 100)  # 0 to 360 deg, unwrapped
    total_deg, rot_count = compute_total_rotation(angles, fps=30.0)
    assert abs(total_deg - 360.0) < 5.0
    assert abs(rot_count - 1.0) < 0.02

def test_total_rotation_triple():
    """Triple jump = 3 rotations = 1080 degrees."""
    from ml.src.analysis.metrics import compute_total_rotation
    angles = np.linspace(0, 6 * np.pi, 300)  # 0 to 1080 deg
    total_deg, rot_count = compute_total_rotation(angles, fps=30.0)
    assert abs(total_deg - 1080.0) < 10.0
    assert abs(rot_count - 3.0) < 0.05

def test_under_rotation_quarter_short():
    """Jump 1/4 rotation short of triple."""
    from ml.src.analysis.metrics import compute_under_rotation
    under = compute_under_rotation(measured_degrees=990.0, target_rotations=3)
    assert abs(under - 90.0) < 1.0  # quarter revolution

def test_under_rotation_clean():
    """Clean triple, no under-rotation."""
    from ml.src.analysis.metrics import compute_under_rotation
    under = compute_under_rotation(measured_degrees=1080.0, target_rotations=3)
    assert abs(under) < 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ml && uv run pytest tests/analysis/test_under_rotation.py -v`
Expected: FAIL — `compute_total_rotation` not defined

- [ ] **Step 3: Implement compute_total_rotation**

Add to `ml/src/analysis/metrics.py`:

```python
def compute_total_rotation(
    shoulder_angles_unwrapped: np.ndarray,
    fps: float,
) -> tuple[float, float]:
    """Compute total rotation from unwrapped shoulder angle series.

    Args:
        shoulder_angles_unwrapped: Unwrapped shoulder axis angles in degrees (N,).
        fps: Frame rate.

    Returns:
        (total_degrees, rotation_count).
    """
    if len(shoulder_angles_unwrapped) < 2:
        return 0.0, 0.0
    total_degrees = float(abs(shoulder_angles_unwrapped[-1] - shoulder_angles_unwrapped[0]))
    rotation_count = total_degrees / 360.0
    return total_degrees, rotation_count


def compute_under_rotation(
    measured_degrees: float,
    target_rotations: float,
) -> float:
    """Compute under-rotation in degrees.

    Args:
        measured_degrees: Measured total rotation in degrees.
        target_rotations: Expected number of rotations (e.g., 3 for triple).

    Returns:
        Under-rotation in degrees. Positive = under-rotated, negative = over-rotated.
    """
    target_degrees = target_rotations * 360.0
    return target_degrees - measured_degrees
```

- [ ] **Step 4: Run tests**

Run: `cd ml && uv run pytest tests/analysis/test_under_rotation.py -v`
Expected: ALL PASS

- [ ] **Step 5: Integrate into BiomechanicalAnalyzer**

Add `compute_total_rotation` call in the analysis pipeline after extracting shoulder angles for the flight phase. Store results as `total_rotation_deg`, `rotation_count`, `under_rotation_deg` metrics.

Add to `ml/src/analysis/metrics_registry.py`:
```python
"total_rotation_deg": MetricDef(display_name="Total Rotation", unit="°", higher_is_better=True),
"rotation_count": MetricDef(display_name="Rotations", unit="", higher_is_better=True),
"under_rotation_deg": MetricDef(display_name="Under-rotation", unit="°", higher_is_better=False),
```

- [ ] **Step 6: Commit**

```bash
git add ml/src/analysis/metrics.py ml/tests/analysis/test_under_rotation.py ml/src/analysis/metrics_registry.py
git commit -m "feat(ml): add total rotation counting and under-rotation detection"
```

---

## WAVE 2: Core Features (Week 1, Days 3-5)

---

### Task 7: Shared API Client [Track B]

**Files:**

- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SessionsApi.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/UsersApi.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/UploadsApi.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/ProcessApi.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/AuthApiTest.kt`

- [ ] **Step 1: Write test for AuthApi.login**

```kotlin
// mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/api/AuthApiTest.kt
package ru.skatelab.shared.api

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class AuthApiTest {
    @Test
    fun loginRequestSerialization() {
        val req = LoginRequest(email = "test@example.com", password = "secret123")
        val json = kotlinx.serialization.json.Json.encodeToString(req)
        assertTrue(json.contains("test@example.com"))
        assertTrue(json.contains("secret123"))
    }
}
```

- [ ] **Step 2: Implement SkateLabClient**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.engine.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json

class SkateLabClient(
    baseUrl: String,
    engine: HttpClientEngine,
) {
    val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    val httpClient = HttpClient(engine) {
        install(ContentNegotiation) { json(json) }
        defaultRequest { url(baseUrl) }
    }

    val auth = AuthApi(httpClient)
    val sessions = SessionsApi(httpClient)
    val users = UsersApi(httpClient)
    val uploads = UploadsApi(httpClient)
    val process = ProcessApi(httpClient)
}
```

- [ ] **Step 3: Implement AuthApi**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt
package ru.skatelab.shared.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.serialization.Serializable
import ru.skatelab.shared.models.TokenResponse

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RegisterRequest(val email: String, val password: String, @kotlinx.serialization.SerialName("display_name") val displayName: String)

class AuthApi(private val client: HttpClient) {
    suspend fun login(email: String, password: String): TokenResponse =
        client.post("/auth/login") {
            contentType(ContentType.Application.Json)
            setBody(LoginRequest(email, password))
        }.body()

    suspend fun register(email: String, password: String, displayName: String): TokenResponse =
        client.post("/auth/register") {
            contentType(ContentType.Application.Json)
            setBody(RegisterRequest(email, password, displayName))
        }.body()

    suspend fun refresh(refreshToken: String): TokenResponse =
        client.post("/auth/refresh") {
            contentType(ContentType.Application.Json)
            setBody(mapOf("refresh_token" to refreshToken))
        }.body()
}
```

- [ ] **Step 4: Implement remaining API classes (SessionsApi, UsersApi, UploadsApi, ProcessApi)**

SessionsApi: `get(id)`, `list(limit, offset)`, `create(videoKey)`, `delete(id)`
UsersApi: `getMe()`, `updateProfile(...)`, `updateSettings(...)`, `uploadAvatar(file)`
UploadsApi: `init(fileName, contentType, totalSize)`, `complete(uploadId, key, parts)`, `presign(fileName, contentType)`
ProcessApi: `queue(sessionId, videoKey)`

- [ ] **Step 5: Run tests**

Run: `cd mobile && ./gradlew :shared:jvmTest`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add mobile/shared/src/
git commit -m "feat(mobile/shared): add Ktor API client with auth, sessions, users, uploads, process"
```

---

### Task 8: Shared Auth + TokenStorage [Track B]

**Files:**

- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/TokenStorage.kt` (expect)
- Create: `mobile/shared/src/androidMain/kotlin/ru/skatelab/shared/auth/AndroidTokenStorage.kt` (actual)
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthInterceptor.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryTest.kt`

- [ ] **Step 1: Define TokenStorage expect**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/TokenStorage.kt
package ru.skatelab.shared.auth

expect class TokenStorage() {
    suspend fun getAccessToken(): String?
    suspend fun getRefreshToken(): String?
    suspend fun saveTokens(access: String, refresh: String)
    suspend fun clearTokens()
}
```

- [ ] **Step 2: Implement Android actual**

```kotlin
// mobile/shared/src/androidMain/kotlin/ru/skatelab/shared/auth/AndroidTokenStorage.kt
package ru.skatelab.shared.auth

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

actual class TokenStorage actual constructor() {
    private var prefs: android.content.SharedPreferences? = null

    fun init(context: Context) {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        prefs = EncryptedSharedPreferences.create(
            context, "skatelab_tokens", masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    actual suspend fun getAccessToken(): String? = prefs?.getString("access_token", null)
    actual suspend fun getRefreshToken(): String? = prefs?.getString("refresh_token", null)
    actual suspend fun saveTokens(access: String, refresh: String) {
        prefs?.edit()?.putString("access_token", access)?.putString("refresh_token", refresh)?.apply()
    }
    actual suspend fun clearTokens() {
        prefs?.edit()?.clear()?.apply()
    }
}
```

- [ ] **Step 3: Implement AuthRepository**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthRepository.kt
package ru.skatelab.shared.auth

import ru.skatelab.shared.api.AuthApi
import ru.skatelab.shared.models.TokenResponse

class AuthRepository(
    private val authApi: AuthApi,
    private val tokenStorage: TokenStorage,
) {
    suspend fun login(email: String, password: String): Result<TokenResponse> = runCatching {
        val tokens = authApi.login(email, password)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        tokens
    }

    suspend fun register(email: String, password: String, displayName: String): Result<TokenResponse> = runCatching {
        val tokens = authApi.register(email, password, displayName)
        tokenStorage.saveTokens(tokens.accessToken, tokens.refreshToken)
        tokens
    }

    suspend fun isLoggedIn(): Boolean = tokenStorage.getAccessToken() != null

    suspend fun logout() { tokenStorage.clearTokens() }

    suspend fun refreshIfNeeded(): String? {
        val refresh = tokenStorage.getRefreshToken() ?: return null
        return runCatching { authApi.refresh(refresh) }
            .getOrNull()
            ?.also { tokenStorage.saveTokens(it.accessToken, it.refreshToken) }
            ?.accessToken
    }
}
```

- [ ] **Step 4: Implement AuthInterceptor (auto token refresh)**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/auth/AuthInterceptor.kt
package ru.skatelab.shared.auth

import io.ktor.client.*
import io.ktor.client.plugins.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*

class AuthInterceptor(
    private val tokenStorage: TokenStorage,
    private val authRepository: AuthRepository,
) : HttpClientPlugin<Unit, AuthInterceptor> {
    override val key = AttributeKey<AuthInterceptor>("AuthInterceptor")

    override fun install(plugin: AuthInterceptor, scope: HttpClient) {
        scope.requestPipeline.intercept(HttpRequestPipeline.State) {
            val token = tokenStorage.getAccessToken()
            if (token != null) {
                context.headers.append(HttpHeaders.Authorization, "Bearer $token")
            }
        }
        scope.responsePipeline.intercept(HttpResponsePipeline.State) {
            if (context.response.status == HttpStatusCode.Unauthorized) {
                val newToken = authRepository.refreshIfNeeded()
                if (newToken != null) {
                    finish()
                    val newRequest = context.request.builder {
                        headers.append(HttpHeaders.Authorization, "Bearer $newToken")
                    }
                    proceedWith(newRequest)
                }
            }
        }
    }

    companion object : HttpClientPluginConfigProvider<Unit, AuthInterceptor> {
        override fun prepare(config: Unit) = AuthInterceptor(tokenStorage, authRepository)
    }
}
```

- [ ] **Step 5: Write test**

```kotlin
// mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/auth/AuthRepositoryTest.kt
package ru.skatelab.shared.auth

import kotlin.test.Test
import kotlin.test.assertTrue

class AuthRepositoryTest {
    @Test
    fun loginRequestFormatsCorrectly() {
        val req = ru.skatelab.shared.api.LoginRequest("a@b.com", "pass")
        val json = kotlinx.serialization.json.Json.encodeToString(req)
        assertTrue(json.contains("a@b.com"))
    }
}
```

- [ ] **Step 6: Run tests**

Run: `cd mobile && ./gradlew :shared:jvmTest`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add mobile/shared/src/
git commit -m "feat(mobile/shared): add auth repository with JWT token storage and refresh interceptor"
```

---

### Task 9: Shared State (ViewModels) [Track B]

**Files:**

- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/SessionsViewModel.kt`
- Create: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/ProcessingViewModel.kt`
- Test: `mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/AuthViewModelTest.kt`

- [ ] **Step 1: Write test**

```kotlin
// mobile/shared/src/commonTest/kotlin/ru/skatelab/shared/state/AuthViewModelTest.kt
package ru.skatelab.shared.state

import kotlin.test.Test
import kotlin.test.assertEquals

class AuthViewModelTest {
    @Test
    fun initialStateIsLoggedOut() {
        val vm = AuthViewModel(MockAuthRepository())
        assertEquals(AuthUiState.LoggedOut, vm.uiState.value)
    }
}
```

- [ ] **Step 2: Implement AuthViewModel**

```kotlin
// mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/AuthViewModel.kt
package ru.skatelab.shared.state

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.shared.auth.AuthRepository

sealed interface AuthUiState {
    data object Loading : AuthUiState
    data object LoggedOut : AuthUiState
    data class LoggedIn(val userId: String, val displayName: String?) : AuthUiState
    data class Error(val message: String) : AuthUiState
}

class AuthViewModel(private val authRepo: AuthRepository) {
    private val _uiState = MutableStateFlow<AuthUiState>(AuthUiState.Loading)
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    suspend fun checkLogin() {
        _uiState.value = if (authRepo.isLoggedIn()) AuthUiState.LoggedIn("cached", null) else AuthUiState.LoggedOut
    }

    suspend fun login(email: String, password: String) {
        authRepo.login(email, password)
            .onSuccess { _uiState.value = AuthUiState.LoggedIn("new", null) }
            .onFailure { _uiState.value = AuthUiState.Error(it.message ?: "Login failed") }
    }

    suspend fun register(email: String, password: String, displayName: String) {
        authRepo.register(email, password, displayName)
            .onSuccess { _uiState.value = AuthUiState.LoggedIn("new", displayName) }
            .onFailure { _uiState.value = AuthUiState.Error(it.message ?: "Registration failed") }
    }

    suspend fun logout() {
        authRepo.logout()
        _uiState.value = AuthUiState.LoggedOut
    }
}
```

- [ ] **Step 3: Implement SessionsViewModel + ProcessingViewModel**

SessionsViewModel: `loadSessions()`, `loadSession(id)` — calls SessionsApi
ProcessingViewModel: `startProcessing(sessionId)`, `observeProgress()` — calls ProcessApi + SSE

- [ ] **Step 4: Run tests**

Run: `cd mobile && ./gradlew :shared:jvmTest`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/src/
git commit -m "feat(mobile/shared): add AuthViewModel, SessionsViewModel, ProcessingViewModel"
```

---

### Task 10: Android Auth Screens [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/SplashScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/LoginScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/AppNavigation.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt`

- [ ] **Step 1: Define type-safe routes**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt
package ru.skatelab.capture.navigation

import kotlinx.serialization.Serializable

@Serializable object SplashRoute
@Serializable object LoginRoute
@Serializable object RegisterRoute
@Serializable object CameraRoute
@Serializable object ResultsRoute
@Serializable data class ResultDetailRoute(val sessionId: String)
@Serializable object ProcessingRoute
@Serializable object ProfileRoute
@Serializable object MoreRoute
```

- [ ] **Step 2: Implement SplashScreen**

Checks token via AuthViewModel, navigates to Login or MainTabs.

- [ ] **Step 3: Implement LoginScreen**

Email + password fields, "Login" button, calls `authViewModel.login()`, navigates to CameraRoute on success.

- [ ] **Step 4: Implement RegisterScreen**

Email + password + displayName fields, "Register" button, calls `authViewModel.register()`, navigates to CameraRoute on success.

- [ ] **Step 5: Wire DI — provide SkateLabClient + AuthViewModel via Hilt**

Update `AppModule.kt` to provide `SkateLabClient` singleton, `AuthRepository`, `AuthViewModel`.

- [ ] **Step 6: Verify build**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 7: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/ mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/ mobile/androidApp/src/main/java/ru/skatelab/capture/di/
git commit -m "feat(mobile): add auth screens (Splash, Login, Register) with type-safe navigation"
```

---

## WAVE 3: Camera + Upload (Week 2, Days 1-3)

---

### Task 11: Android Camera Screen [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabs.kt`

- [ ] **Step 1: Implement MainTabs scaffold**

4-tab `NavigationBar`: Camera, Results, Profile, More. Each tab hosts a NavGraph.

- [ ] **Step 2: Implement CameraScreen**

Reuse existing `CameraXRecorder` and `CameraRepositoryImpl`. Compose UI with:
- CameraX PreviewView
- Record button (toggle)
- BLE indicator (optional, shows connected sensors)
- "Record without sensors" always available

- [ ] **Step 3: Implement CameraViewModel**

State: `isRecording`, `videoFile`, `bleConnected`. On recording stop: save file, create `PendingUpload` in Room, enqueue `UploadWorker`, navigate to `ProcessingRoute`.

- [ ] **Step 4: Verify build**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/ mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/
git commit -m "feat(mobile): add camera screen with tab navigation and optional BLE indicator"
```

---

### Task 12: Room Database + UploadWorker [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadEntity.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/CachedSessionEntity.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/ChunkedUploader.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt`

- [ ] **Step 1: Define Room entities**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadEntity.kt
package ru.skatelab.capture.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey val id: String,
    val videoPath: String,
    val imuLeftPath: String? = null,
    val imuRightPath: String? = null,
    val manifestPath: String? = null,
    val status: String = "READY",  // READY, UPLOADING, PROCESSING, COMPLETED, FAILED
    val uploadId: String? = null,
    val r2Key: String? = null,
    val sessionId: String? = null,
    val retryCount: Int = 0,
    val createdAt: Long = System.currentTimeMillis(),
)
```

- [ ] **Step 2: Define AppDatabase**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt
package ru.skatelab.capture.data.db

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(entities = [PendingUploadEntity::class, CachedSessionEntity::class], version = 1)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingUploadDao(): PendingUploadDao
    abstract fun cachedSessionDao(): CachedSessionDao
}
```

- [ ] **Step 3: Implement ChunkedUploader**

Port web's `ChunkedUploader` (frontend/src/lib/api/uploads.ts) to Kotlin:
1. `POST /uploads/init` → presigned URLs
2. `PUT` parts concurrently (3) → collect ETags
3. `POST /uploads/complete` → finalize

Use Ktor `HttpStatement` for part uploads with progress callback.

- [ ] **Step 4: Implement UploadWorker**

```kotlin
// mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt
package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.*
import ru.skatelab.capture.data.db.AppDatabase

class UploadWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val uploadId = inputData.getString("upload_id") ?: return Result.failure()
        val db = AppDatabase.getInstance(applicationContext)
        val entity = db.pendingUploadDao().getById(uploadId) ?: return Result.failure()

        return try {
            // 1. Upload video via ChunkedUploader
            setForeground(getForegroundInfo("Uploading video..."))
            val videoKey = ChunkedUploader(applicationContext).upload(entity.videoPath)

            // 2. Upload IMU files (if any)
            val imuLeftKey = entity.imuLeftPath?.let { ChunkedUploader(applicationContext).upload(it) }
            val imuRightKey = entity.imuRightPath?.let { ChunkedUploader(applicationContext).upload(it) }

            // 3. Create session
            setForeground(getForegroundInfo("Creating session..."))
            val session = client.sessions.create(videoKey = videoKey, imuLeftKey = imuLeftKey, imuRightKey = imuRightKey)

            // 4. Start ML processing
            setForeground(getForegroundInfo("Starting analysis..."))
            client.process.queue(sessionId = session.id, videoKey = videoKey)

            // 5. Update Room
            db.pendingUploadDao().updateStatus(uploadId, "PROCESSING", sessionId = session.id)
            Result.success()
        } catch (e: Exception) {
            db.pendingUploadDao().incrementRetry(uploadId)
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }
}
```

- [ ] **Step 5: Wire DI — provide Room database**

- [ ] **Step 6: Verify build**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 7: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/ mobile/androidApp/src/main/java/ru/skatelab/capture/upload/ mobile/androidApp/src/main/java/ru/skatelab/capture/di/
git commit -m "feat(mobile): add Room database, ChunkedUploader, and UploadWorker for offline uploads"
```

---

### Task 13: Android Processing + SSE [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingViewModel.kt`

- [ ] **Step 1: Implement ProcessingScreen**

Shows progress bar + status message. Observes SSE events from ProcessApi.
On `COMPLETED` status: navigate to `ResultDetailRoute(sessionId)`.

- [ ] **Step 2: Implement ProcessingViewModel**

Observes Room `PendingUploadEntity` status. When status = PROCESSING, connects to SSE stream via `ProcessApi.stream(taskId)`. Updates progress from `ProcessEvent`.

- [ ] **Step 3: Verify build**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/
git commit -m "feat(mobile): add processing screen with SSE progress streaming"
```

---

### Task 14: Android Session List + Detail [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/MetricCard.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListViewModel.kt`
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailViewModel.kt`

- [ ] **Step 1: Implement MetricCard composable**

Displays: metric name, value, unit, PR badge, reference range indicator. Accepts `SessionMetricResponse`.

- [ ] **Step 2: Implement SessionListScreen**

LazyColumn of session cards (thumbnail, element type, score, date). Pull-to-refresh. Calls `SessionsViewModel.loadSessions()`.

- [ ] **Step 3: Implement SessionDetailScreen**

Layout:
- Top: ExoPlayer video player (reuse existing from `SessionDetailScreen.kt:58-86`)
- Below video: Element type badge (auto-classified)
- Metric cards: Jump Height, Airtime, Angular Velocity, Peak Angular Velocity, Time to Peak, Rotation Count, Under-rotation, Landing Quality, GOE Proxy
- Chart: Vico `CartesianChartHost` for angular velocity over time
- (Optional) IMU charts if data present

- [ ] **Step 4: Implement ViewModels**

SessionListViewModel: loads `GET /sessions`, caches in Room
SessionDetailViewModel: loads `GET /sessions/{id}`, exposes metrics list + video URL

- [ ] **Step 5: Verify build**

Run: `cd mobile && ./gradlew :androidApp:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/
git commit -m "feat(mobile): add session list and detail screens with metric cards and charts"
```

---

### Task 15: ML — Jump Type Classifier [Track D]

**Files:**

- Modify: `ml/src/tas/classifier.py` — train SegmentClassifier on available data
- Modify: `ml/src/tas/inference.py` — wire fine classifier into TASElementSegmenter
- Modify: `ml/src/analysis/element_defs.py` — add rotation counts for multi-rotation variants
- Test: `ml/tests/analysis/test_jump_classifier.py`

- [ ] **Step 1: Create rule-based fallback classifier**

Since labeled figure skating data is scarce, implement a rule-based classifier using `ElementDef` metadata (rotation count + toe pick detection):

```python
# ml/src/analysis/jump_classifier.py
from ml.src.analysis.element_defs import ELEMENT_DEFS

def classify_jump(
    rotation_count: float,
    has_toe_pick_signal: bool,
    takeoff_direction: str = "backward",  # forward/backward
) -> tuple[str, float]:
    """Classify jump type from biomechanical features.

    Returns (element_name, confidence).
    """
    candidates = []
    for elem in ELEMENT_DEFS.values():
        if elem.name == "three_turn":
            continue
        score = 0.0
        # Rotation match (most important)
        if abs(rotation_count - elem.rotations) < 0.3:
            score += 0.6
        elif abs(rotation_count - elem.rotations) < 0.6:
            score += 0.3
        # Toe pick match
        if has_toe_pick_signal == elem.has_toe_pick:
            score += 0.25
        # Direction match (axel = forward takeoff)
        if elem.name == "axel" and takeoff_direction == "forward":
            score += 0.15
        if elem.name != "axel" and takeoff_direction == "backward":
            score += 0.05
        candidates.append((elem.name, score))

    if not candidates:
        return "unknown", 0.0
    best = max(candidates, key=lambda x: x[1])
    return best[0], min(best[1], 1.0)
```

- [ ] **Step 2: Write test**

```python
def test_classify_triple_toe_loop():
    name, conf = classify_jump(rotation_count=3.0, has_toe_pick_signal=True)
    assert name == "toe_loop"
    assert conf > 0.7

def test_classify_double_axel():
    name, conf = classify_jump(rotation_count=2.5, has_toe_pick_signal=False, takeoff_direction="forward")
    assert name == "axel"
    assert conf > 0.7
```

- [ ] **Step 3: Wire into metrics pipeline**

Add `classify_jump()` call in BiomechAnalyzer after computing rotation_count. Store as `jump_type` metric.

- [ ] **Step 4: Add jump_type to metrics_registry**

```python
"jump_type": MetricDef(display_name="Jump Type", unit="", higher_is_better=True),
```

- [ ] **Step 5: Commit**

```bash
git add ml/src/analysis/jump_classifier.py ml/src/analysis/metrics.py ml/src/analysis/metrics_registry.py ml/tests/analysis/test_jump_classifier.py
git commit -m "feat(ml): add rule-based jump type classifier (axel/lutz/flip/loop/salchow/toe_loop)"
```

---

### Task 16: ML — Spin Detection [Track D]

**Files:**

- Create: `ml/src/analysis/spin_classifier.py`
- Modify: `ml/src/analysis/element_defs.py` — add spin type definitions
- Modify: `ml/src/analysis/metrics_registry.py` — add spin metrics
- Test: `ml/tests/analysis/test_spin_classifier.py`

- [ ] **Step 1: Add spin type definitions**

In `element_defs.py`, add:
```python
SPIN_TYPES = {
    "upright_spin": SpinDef(name="upright_spin", name_ru="Вертикальное вращение", min_duration_s=1.0, hip_y_range_max=0.1),
    "one_foot_spin": SpinDef(name="one_foot_spin", name_ru="Вращение на одной ноге", min_duration_s=1.0, hip_y_range_max=0.15),
    "scratch_spin": SpinDef(name="scratch_spin", name_ru="Скрестное вращение", min_duration_s=1.5, hip_y_range_max=0.2),
}
```

- [ ] **Step 2: Implement spin classifier**

Rule-based: if TAS coarse label = "Spin" and duration > min_duration, classify by hip_y_range pattern.

- [ ] **Step 3: Add spin metrics to registry**

```python
"spin_type": MetricDef(display_name="Spin Type", unit="", higher_is_better=True),
"spin_peak_velocity": MetricDef(display_name="Peak Spin Velocity", unit="°/с", higher_is_better=True),
```

- [ ] **Step 4: Commit**

```bash
git add ml/src/analysis/spin_classifier.py ml/src/analysis/element_defs.py ml/src/analysis/metrics_registry.py ml/tests/analysis/test_spin_classifier.py
git commit -m "feat(ml): add spin type detection (upright, one-foot, scratch)"
```

---

## WAVE 4: Integration + Polish (Week 3)

---

### Task 17: Skeleton Overlay [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/skeleton/SkeletonOverlay.kt`

Port web's `SkeletonCanvas.tsx` H3.6M 17-keypoint drawing logic to Compose Canvas.

- [ ] **Step 1: Implement SkeletonOverlay composable**

```kotlin
// H3.6M connections (same as web)
val CONNECTIONS = listOf(
    intArrayOf(0, 1), intArrayOf(1, 2), intArrayOf(2, 3),   // Right leg
    intArrayOf(0, 4), intArrayOf(4, 5), intArrayOf(5, 6),   // Left leg
    intArrayOf(0, 7), intArrayOf(7, 8), intArrayOf(8, 9), intArrayOf(9, 10),  // Spine + head
    intArrayOf(9, 11), intArrayOf(11, 12), intArrayOf(12, 13),  // Left arm
    intArrayOf(9, 14), intArrayOf(14, 15), intArrayOf(15, 16),  // Right arm
)
```

Compose `Canvas` composable overlaid on ExoPlayer. Accepts `PoseData` (frame-indexed keypoints) and `currentFrame`. Draws bone connections + joint circles with color coding.

- [ ] **Step 2: Add toggle button in SessionDetailScreen**

"Show skeleton" toggle. When enabled, overlays `SkeletonOverlay` on video.

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/skeleton/ mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt
git commit -m "feat(mobile): add 2D skeleton overlay on video playback"
```

---

### Task 18: Profile + Settings Screens [Track C]

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabs.kt`

- [ ] **Step 1: Implement ProfileScreen**

Display: avatar, display name, email, stats. Editable fields: display name, bio, height, weight. Angular unit selector (°/с / об/с / RPM). "Logout" button.

- [ ] **Step 2: Implement MoreScreen**

BLE settings (scan, calibrate), App info, Logout.

- [ ] **Step 3: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/
git commit -m "feat(mobile): add profile screen with angular unit preference"
```

---

### Task 19: BLE Integration (Kable) [Track B/C]

**Files:**

- Modify: `mobile/shared/build.gradle.kts` — add Kable dependency
- Modify: `mobile/androidApp/build.gradle.kts` — add Kable dependency
- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/KableBleRepository.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/AppModule.kt` — provide KableBleRepository or NoOpBleRepository

- [ ] **Step 1: Add Kable dependency**

```kotlin
// In shared/build.gradle.kts commonMain:
implementation("com.juul.kable:core:2.3.1")
```

- [ ] **Step 2: Implement KableBleRepository**

Wrap Kable `Scanner`, `Peripheral` API to match existing `BleRepository` interface. Uses `peripheral.observe()` for WT901 notifications → feeds `Wt901Parser`.

- [ ] **Step 3: Implement NoOpBleRepository**

Returns empty flows, no-op connect/disconnect. Used when BLE unavailable.

- [ ] **Step 4: Update CameraViewModel**

Make BLE optional: if `bleAvailability.connectedSensors.value.isNotEmpty()`, start IMU collection. Otherwise skip.

- [ ] **Step 5: Test with real WT901 sensor**

Manual test: connect sensor, record video with IMU, verify upload includes .binpb files.

- [ ] **Step 6: Commit**

```bash
git add mobile/shared/build.gradle.kts mobile/androidApp/src/main/java/ru/skatelab/capture/data/ble/ mobile/androidApp/src/main/java/ru/skatelab/capture/di/
git commit -m "feat(mobile): integrate Kable BLE library with optional IMU recording"
```

---

### Task 20: Backend Schema Integration [Track A]

**Files:**

- Modify: `backend/app/schemas.py` — add new metric names to `SessionMetricResponse` validation
- Modify: `ml/gpu_server/server.py` — load jump classifier + spin classifier models
- Modify: `ml/gpu_server/Containerfile` — add new model files to image

- [ ] **Step 1: Add new metric names to METRIC_REGISTRY**

Ensure `jump_type`, `spin_type`, `rotation_count`, `under_rotation_deg`, `total_rotation_deg`, `time_to_peak`, `landing_quality` are in the registry.

- [ ] **Step 2: Wire ML outputs into ProcessResponse**

In `worker.py` and GPU server response, include new metric fields.

- [ ] **Step 3: Update GPU server Containerfile**

Add classifier model files to the image build.

- [ ] **Step 4: E2E test**

Upload video via mobile → process → verify all new metrics appear in response.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py ml/src/analysis/metrics_registry.py ml/gpu_server/ backend/app/worker.py
git commit -m "feat(backend): wire jump classifier and spin detection into ML pipeline responses"
```

---

### Task 21: Offline Resilience + Polish [Track C]

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt`
- Modify: various UI files for error states

- [ ] **Step 1: Add network constraints to UploadWorker**

```kotlin
val constraints = Constraints.Builder()
    .setRequiredNetworkType(NetworkType.CONNECTED)
    .setRequiresBatteryNotLow(true)
    .build()
val workRequest = OneTimeWorkRequestBuilder<UploadWorker>()
    .setConstraints(constraints)
    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
    .build()
```

- [ ] **Step 2: Add error states to all screens**

Login error, upload error, processing error, network error. Snackbar or inline error display.

- [ ] **Step 3: Add pull-to-refresh on SessionListScreen**

- [ ] **Step 4: Add loading states (shimmer/progress)**

- [ ] **Step 5: Test offline flow**

Airplane mode → record video → turn on network → verify auto-upload via WorkManager.

- [ ] **Step 6: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/
git commit -m "fix(mobile): add offline resilience, error states, pull-to-refresh"
```

---

### Task 22: Mobile CI Workflow [Track A]

**Files:**

- Create: `.github/workflows/mobile.yml`
- Modify: `.github/workflows/android.yml` — rename or replace

- [ ] **Step 1: Create mobile.yml with KMP support**

Replaces `android.yml`. Adds `shared-test` job (JVM), Kover coverage upload, path-based triggers for `:shared` vs `:androidApp`.

- [ ] **Step 2: Verify CI triggers correctly**

Push a change to `mobile/shared/` → only shared-test runs. Push to `mobile/androidApp/` → only android-test runs.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mobile.yml
git rm .github/workflows/android.yml
git commit -m "ci: replace android.yml with mobile.yml supporting KMP shared module tests"
```

---

## Self-Review

**1. Spec coverage:**

| Spec requirement | Task |
|------------------|------|
| KMP + native UI | Task 1 (scaffold), 7-9 (shared) |
| Server-side ML | Task 20 (integration) |
| Optional BLE/IMU | Task 19 (Kable) |
| Video recording | Task 11 (Camera) |
| Chunked upload | Task 12 (UploadWorker) |
| SSE progress | Task 13 (Processing) |
| Session list/detail | Task 14 |
| Metric cards | Task 14 |
| Skeleton overlay | Task 17 |
| Auth flow | Task 10 |
| Profile + settings | Task 18 |
| Angular unit preference | Task 3 (backend), Task 18 (UI) |
| Avatar upload | Task 4 |
| Jump classification | Task 15 |
| Spin detection | Task 16 |
| Under-rotation | Task 6 |
| GOE proxy | Already exists in ML pipeline |
| Offline resilience | Task 21 |
| CI/CD | Task 22 |

**2. Placeholder scan:** No TBD/TODO found. All steps have code.

**3. Type consistency:** `TokenResponse`, `SessionResponse`, `SessionMetricResponse`, `ProcessEvent` defined in Task 2, used consistently in Tasks 7-14. `LoginRequest`/`RegisterRequest` defined in Task 7, used in Task 8-10. Routes defined in Task 10, used throughout.
