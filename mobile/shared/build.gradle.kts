plugins {
    id("kmp-library-convention")
    id("serialization-convention")
    alias(libs.plugins.kover)
}

kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(libs.kotlinx.coroutines.core)
            implementation(libs.kotlinx.serialization.json)
            implementation(libs.kotlinx.datetime)
            implementation(libs.ktor.client.core)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.json)
            implementation(libs.ktor.client.auth)
            implementation(libs.ktor.client.sse)
            implementation(libs.multiplatform.settings)
        }
        androidMain.dependencies {
            implementation(libs.ktor.client.okhttp)
            implementation(libs.security.crypto)
        }
        iosMain.dependencies {
            implementation("io.ktor:ktor-client-darwin:${libs.versions.ktor.get()}")
            implementation(libs.multiplatform.settings.keychain)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.ktor.client.mock)
            implementation(libs.turbine)
        }
    }
}

android {
    compileSdk = 35
    defaultConfig { minSdk = 24 }
    namespace = "ru.skatelab.shared"
}
