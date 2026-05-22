dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    versionCatalogs {
        create("libs") {
            from(files("gradle/libs-convention.versions.toml"))
        }
    }
}

rootProject.name = "build-logic"
include(":convention")
