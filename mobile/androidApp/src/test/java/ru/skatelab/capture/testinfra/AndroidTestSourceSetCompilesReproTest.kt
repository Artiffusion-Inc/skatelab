package ru.skatelab.capture.testinfra

import java.io.File
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Repro for issue #332 — `:androidApp:compileDebugAndroidTestKotlin` does not compile, blocking the
 * ENTIRE androidTest source set (no instrumented test runnable, no Compose screen-test, no a11y).
 *
 * This is a **source-contract** repro (not a runtime test): it statically inspects the two known
 * broken androidTest source files and asserts the defect patterns are present. RED now = the
 * broken patterns exist → compilation fails (proven by `gradlew :androidApp:compileDebugAndroidTestKotlin`
 * → BUILD FAILED with the errors listed below). After the #332 fix (correct imports / updated
 * `PersonalRecord` calls / removed or repaired files), these patterns disappear and the test goes
 * GREEN — which is the signal that `compileDebugAndroidTestKotlin` would build.
 *
 * Why a source-contract test instead of invoking the Gradle task: running
 * `:androidApp:compileDebugAndroidTestKotlin` from inside a JUnit test is heavy and flaky (Gradle
 * tooling API, daemon, classpath). A static check on the two files is deterministic, fast, and
 * directly pins the two root-cause defects documented in #332 — and serves as a regression-magnet
 * so the broken patterns do not silently return.
 *
 * Verified errors (reproduced 2026-06-25, current code):
 *
 *   1. UploadWorkerTest.kt — `import kotlin.test.Test` / `import kotlin.test.assertEquals` /
 *      `@RunWith(AndroidJUnit4::class)`. `kotlin.test` is NOT resolvable in the androidTest source
 *      set (no `androidTestImplementation("org.jetbrains.kotlin:kotlin-test")`), so the compiler
 *      reports `Unresolved reference 'test'/'RunWith'/'Test'/'assertEquals'`. Should be
 *      `org.junit.Test` / `org.junit.Assert.assertEquals`.
 *
 *        e: UploadWorkerTest.kt:4:15 Unresolved reference 'test'
 *        e: UploadWorkerTest.kt:16:2  Unresolved reference 'RunWith'
 *        e: UploadWorkerTest.kt:18:6  Unresolved reference 'Test'
 *        e: UploadWorkerTest.kt:22:9  Unresolved reference 'assertEquals'
 *
 *   2. DashboardScreenTest.kt:42 — `PersonalRecord(elementType = "axel", value = 0.85,
 *      sessionId = "s1")` omits the REQUIRED `metricName` parameter (PersonalRecord.metricName is
 *      non-nullable, no default — MetricsModels.kt:46-51). Compiler reports
 *      `No value passed for parameter 'metricName'`.
 *
 *        e: DashboardScreenTest.kt:42:68 No value passed for parameter 'metricName'.
 *
 * Contract: after the fix, neither defect pattern may remain in these files.
 */
class AndroidTestSourceSetCompilesReproTest {
    private val androidTestRoot =
        File("src/androidTest/java/ru/skatelab/capture")

    private fun file(relPath: String): File =
        File(androidTestRoot, relPath).also {
            assertTrue(
                "androidTest source file should exist: ${it.path} (cwd=${File(".").absolutePath})",
                it.exists(),
            )
        }

    @Test
    fun uploadWorkerTest_mustNotUseUnresolvableKotlinTestImports_repro332() {
        // #332 defect 1: kotlin.test imports are unresolvable in androidTest source set.
        val src = file("upload/UploadWorkerTest.kt").readText()

        assertFalse(
            "BUG #332: UploadWorkerTest.kt imports `kotlin.test.*`, which is unresolvable in the " +
                "androidTest source set (no kotlin-test dependency). Use org.junit.Test / " +
                "org.junit.Assert.assertEquals. Found kotlin.test imports — compilation fails.",
            src.contains("import kotlin.test.Test") || src.contains("import kotlin.test.assertEquals"),
        )
    }

    @Test
    fun dashboardScreenTest_personalRecordCallsMustPassMetricName_repro332() {
        // #332 defect 2: PersonalRecord(...) calls omit the required `metricName` parameter.
        val src = file("ui/dashboard/DashboardScreenTest.kt").readText()

        // A PersonalRecord(...) call that omits metricName (no `metricName =` before the closing
        // paren of that call). We detect a call that has NO metricName kwarg at all.
        val personalRecordCalls =
            Regex("""PersonalRecord\s*\(([^)]*)\)""", RegexOption.DOT_MATCHES_ALL)
                .findAll(src)
                .map { it.groupValues[1] }
                .toList()
        assertTrue(
            "Test sanity: expected at least one PersonalRecord(...) call in DashboardScreenTest.kt",
            personalRecordCalls.isNotEmpty(),
        )
        val callsMissingMetricName = personalRecordCalls.filter { !it.contains("metricName") }
        assertFalse(
            "BUG #332: DashboardScreenTest.kt has PersonalRecord(...) call(s) without the required " +
                "`metricName` kwarg — compilation fails with " +
                "`No value passed for parameter 'metricName'`. Missing in: $callsMissingMetricName",
            callsMissingMetricName.isNotEmpty(),
        )
    }
}
