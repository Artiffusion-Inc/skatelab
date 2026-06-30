package ru.skatelab.capture.ui.auth

import java.io.File
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * RED repro for NEW bug — auth screens (RegisterScreen / LoginScreen) never render the
 * actionable `AppError.Conflict.detail` ("Email already registered") on a 409 register/login
 * conflict; instead they fall back to the generic localized `error_unknown`
 * ("An unexpected error occurred."). Reported by a real user on the Android APK:
 * registering with an already-existing email shows "An unexpected error occurred" instead of
 * "Email already registered" / "Конфликт аккаунта."
 *
 * Root cause (two layers, only the first was fixed):
 *
 *   1. (FIXED in #337/#363) `ExceptionMapping.toAppError()` now maps HTTP 409 →
 *      `AppError.Conflict(detail)` carrying the backend's "Email already registered" text, and
 *      `AuthApi.register` throws `ResponseException` with the parsed body detail. The shared
 *      `RegisterConflictDetailLostReproTest` is GREEN. So by the time the error reaches the
 *      Android screen, `uiState.error` IS `AppError.Conflict("Email already registered")`.
 *
 *   2. (STILL BROKEN — this bug) `RegisterScreen` (RegisterScreen.kt:118-130) and `LoginScreen`
 *      (LoginScreen.kt:114-126) render errors with a hand-written `when` that has NO
 *      `AppError.Conflict` branch:
 *
 *        when {
 *          error is AppError.Unknown && error.detail != null -> "…: ${error.detail}"
 *          error is AppError.Network -> …
 *          error is AppError.Auth -> …
 *          error is AppError.Timeout -> …
 *          error is AppError.Server -> …
 *          error is AppError.NotFound -> …
 *          else -> stringResource(R.string.error_unknown)   // ← 409 Conflict lands HERE
 *        }
 *
 *      `AppError.Conflict` matches none of the named branches → `else` → the generic
 *      `error_unknown` string. The actionable conflict detail is discarded at the LAST mile —
 *      the screen — even though every layer below it preserved it.
 *
 *      A correct helper already exists: `AppError.localizedMessage()`
 *      (utils/AppErrorExt.kt:30-39) handles `Conflict -> detail ?: error_conflict` and is used
 *      by `ProfileViewModel`. The auth screens were NOT migrated to it in #363 (that PR touched
 *      only `AppErrorExt`, `AuthApi`, `AppError`, `ExceptionMapping`, strings + the ViewModel
 *      repro — it never edited `RegisterScreen.kt` / `LoginScreen.kt`). So the fix the PR
 *      claimed ("preserve register 409 conflict detail") does not actually reach the user on the
 *      auth screens.
 *
 * This repro pins the contract statically (no emulator/Robolectric needed): the auth screens'
 * error-render code must handle `AppError.Conflict` — either via a dedicated branch surfacing
 * `error.detail`/`error_conflict`, or by delegating to `AppError.localizedMessage()`. RED now:
 * neither screen references `AppError.Conflict` (or `localizedMessage`) in its error `when`.
 * After the fix → GREEN.
 *
 * Why a static check: Compose `when`-dispatch over a sealed type is a compile-time-exhaustive
 * decision that the source fully determines; whether `AppError.Conflict` is routed is a property
 * of the source text, not runtime state. A source assertion is deterministic and CI-cheap, the
 * same pattern used by prior static-assertion repros.
 */
class RegisterConflictUiFallbackToUnknownReproTest {
    private val screens =
        listOf(
            "mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt",
            "mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/LoginScreen.kt",
        )

    @Test
    fun auth_screens_render_conflict_detail_not_generic_unknown_repro() {
        val repoRoot = findRepoRoot()
        screens.forEach { rel ->
            val src = File(repoRoot, rel).readText()
            // The screen must surface AppError.Conflict (dedicated branch) OR delegate to the
            // shared localizedMessage() helper (which handles Conflict). A bare `when` that only
            // names Unknown/Network/Auth/Timeout/Server/NotFound + `else` drops Conflict into
            // `else -> error_unknown`.
            val handlesConflict =
                src.contains("AppError.Conflict") || src.contains("localizedMessage(")
            assertTrue(
                "BUG: $rel renders auth errors with a `when` that has no `AppError.Conflict` " +
                    "branch and does not call `AppError.localizedMessage()`. A 409 register/login " +
                    "conflict (\"Email already registered\") reaches the screen as " +
                    "AppError.Conflict but matches no branch → `else -> error_unknown` → the user " +
                    "sees \"An unexpected error occurred\" instead of the actionable conflict " +
                    "detail. #337/#363 fixed ExceptionMapping but never migrated the auth screens. " +
                    "Fix: add an `AppError.Conflict -> error.detail ?: error_conflict` branch or " +
                    "delegate to `AppError.localizedMessage()`.",
                handlesConflict,
            )
        }
    }

    private fun findRepoRoot(): File {
        // test working dir is androidApp/; repo root is two parents up (mobile/../ repo, or the
        // mobile/ dir itself). Resolve by locating the screen file.
        var dir = File(".").canonicalFile
        repeat(6) {
            if (File(dir, "mobile/androidApp/src/main/java/ru/skatelab/capture/ui/auth/RegisterScreen.kt").exists()) {
                return dir
            }
            val parent = dir.parentFile
            if (parent == null) {
                throw AssertionError("repo root not found from ${File(".").canonicalPath}")
            }
            dir = parent
        }
        throw AssertionError("repo root not found from ${File(".").canonicalPath}")
    }
}
