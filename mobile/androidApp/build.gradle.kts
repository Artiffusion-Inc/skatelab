plugins {
    id("android-app-convention")
    id("serialization-convention")
    alias(libs.plugins.protobuf)
    alias(libs.plugins.kover)
}

android {
    namespace = "ru.skatelab.capture"
    defaultConfig {
        buildConfigField("String", "API_BASE_URL", "\"${System.getenv("API_BASE_URL") ?: "https://api.skatelab.ru/v1/"}\"")
        applicationId = "ru.skatelab.capture"
        versionCode = 1
        versionName = "1.0.0"
        targetSdk = 35

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    ksp {
        arg("room.schemaLocation", "$projectDir/schemas")
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    tasks.withType<Test>().configureEach {
        jvmArgs = listOf("-Xmx768m", "-XX:+UseG1GC", "-XX:MaxMetaspaceSize=256m")
        maxHeapSize = "768m"
        maxParallelForks = 1
    }

    protobuf {
        protoc {
            artifact = "com.google.protobuf:protoc:${libs.versions.protobuf.get()}"
        }
        generateProtoTasks {
            all().forEach { task ->
                task.builtins {
                    create("java") {
                        option("lite")
                    }
                }
            }
        }
    }
}

dependencies {
    implementation(project(":shared"))

    // Compose BOM
    val composeBom = platform(libs.compose.bom)
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    // AndroidX
    implementation(libs.core.ktx)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.activity.compose)
    implementation(libs.navigation.compose)
    implementation(libs.kotlinx.serialization.json)

    // Ktor (for DI-provided SkateLabClient)
    implementation(libs.ktor.client.okhttp)
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // Multiplatform-settings (for TokenStorage)
    implementation(libs.multiplatform.settings)

    // Room
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    // WorkManager
    implementation(libs.work.runtime.ktx)
    implementation(libs.hilt.work)
    ksp(libs.hilt.compiler)

    // Hilt (KSP — migrated from kapt)
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    // CameraX
    implementation(libs.camerax.core)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.video)
    implementation(libs.camerax.compose)

    // Media3 ExoPlayer
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.ui)

    // Vico charts
    implementation(libs.vico.compose)
    implementation(libs.vico.compose.m3)

    // Protobuf
    implementation(libs.protobuf.javalite)

    // Coroutines
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.coroutines.play.services)
    implementation(libs.kotlinx.coroutines.guava)

    // Kable BLE
    implementation(libs.kable.core)

    // Testing
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.mockk)
    testImplementation(libs.turbine)
    testImplementation(libs.json)
    androidTestImplementation(composeBom)
    androidTestImplementation(libs.test.ext.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4-accessibility:1.8.2")
    androidTestImplementation(libs.test.runner)
    androidTestImplementation(libs.test.rules)
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
