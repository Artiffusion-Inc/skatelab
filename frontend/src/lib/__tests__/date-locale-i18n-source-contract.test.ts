/**
 * Repro (source-contract) — date formatting is hardcoded to `"ru-RU"` across
 * user-facing components, ignoring the user's selected language (next-intl).
 *
 * The app is i18n (next-intl, ru/en) and exposes `useLocale()` from `@/i18n`.
 * The settings page lets the user switch language. But date formatting in
 * multiple components is hardcoded to the Russian locale:
 *
 *   new Date(...).toLocaleDateString("ru-RU"[, {...}])
 *
 * So when a user selects English in settings, every date on the session detail,
 * student cards, session comparison, recent activity, element cards, and
 * progress screens STILL renders in Russian ("25 июня 2026 г." instead of
 * "June 25, 2026"). This breaks i18n consistency.
 *
 * The correct pattern: use `useLocale()` from `next-intl` and pass it (or a
 * derived BCP-47 tag) to `toLocaleDateString` / `Intl.DateTimeFormat`. Today
 * NO component does this — the hardcoded `"ru-RU"` is systemic, not a one-off.
 *
 * This is a SOURCE-CONTRACT repro (like the backend #332 androidTest source-set
 * test): it statically scans the known user-facing component files and asserts
 * the hardcoded-locale pattern is absent. RED now: the files contain
 * `toLocaleDateString("ru-RU"` → the scan fails. After the fix (each file uses
 * `useLocale()`), the hardcoded literal disappears and the test goes GREEN.
 *
 * A source-contract test is used (rather than rendering each component) because
 * the defect is a literal-string pattern, deterministic, and spans many files;
 * pinning the absence of the pattern is a clean regression magnet and directly
 * documents the contract (dates must respect the selected locale).
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

// User-facing components that render dates and were found to hardcode "ru-RU".
const FILES_WITH_DATES = [
  "src/components/coach/student-card.tsx",
  "src/components/session/session-comparison.tsx",
  "src/components/progress/element-card.tsx",
  "src/components/profile/recent-activity.tsx",
  "src/app/(app)/sessions/[id]/page.tsx",
]

function readSrc(rel: string): string {
  // vitest runs with cwd = the frontend project root.
  return readFileSync(resolve(process.cwd(), rel), "utf8")
}

describe("date formatting respects selected locale (i18n source-contract repro)", () => {
  it("no user-facing component hardcodes toLocaleDateString('ru-RU')", () => {
    const offenders: string[] = []
    for (const rel of FILES_WITH_DATES) {
      const src = readSrc(rel)
      if (/toLocaleDateString\(\s*["']ru-RU["']/.test(src)) {
        offenders.push(rel)
      }
    }

    expect(offenders, `BUG (i18n): these files hardcode "ru-RU" date locale, ` +
      `ignoring the user's selected language (useLocale). English users see ` +
      `Russian dates. Use useLocale() from next-intl instead. Offenders: ` +
      `${offenders.join(", ")}`).toEqual([])
  })
})