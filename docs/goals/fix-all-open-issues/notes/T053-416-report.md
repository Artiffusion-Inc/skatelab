# T053 report — Fix #416 (i18n residual)

Status: **DONE**

Commits (on branch `worktree-fix-i18n-residual-416`):
- `3ed116f2` — `fix(mobile): SessionListScreen uses AppError.localizedMessage not raw messageKey (#416)`
- `7f40e7b7` — `fix(frontend): localize offer/terms pages via getTranslations (#416)`

## Site A — mobile SessionListScreen raw messageKey

File: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionListScreen.kt`

Edits:
1. Added import (lexicographically ordered after `ru.skatelab.capture.ui.metrics.metricLabel`):
   ```kotlin
   import ru.skatelab.capture.utils.localizedMessage
   ```
2. Error block (was :123 `val message = (uiState as SessionsUiState.Error).error.messageKey` + `Text(message, ...)`):
   removed the `val message = ...messageKey` line and replaced `Text(message, ...)` with
   ```kotlin
   Text(
       (uiState as SessionsUiState.Error).error.localizedMessage(),
       style = MaterialTheme.typography.bodyMedium,
       color = MaterialTheme.colorScheme.onSurfaceVariant,
   )
   ```
   Matches the existing pattern in DashboardScreen:91, SessionDetailScreen:122, MetricTrendScreen:140.

Verify:
- `grep -n "messageKey" SessionListScreen.kt` → empty (exit 1, no matches).
- Docker `:androidApp:testDebugUnitTest ktlintCheck --no-daemon --no-configuration-cache` → `BUILD SUCCESSFUL in 6m 24s`.

### ktlint import-order hiccup (self-corrected)
First mobile build failed `ktlintMainSourceSetCheck`: my initial import line was inserted between
`androidx.compose.ui.semantics.role` and `androidx.compose.ui.semantics.semantics`, breaking
ktlint's lexicographic-order rule. Re-placed the `ru.skatelab.capture.utils.localizedMessage`
import with the other `ru.skatelab.*` imports (after `ru.skatelab.capture.ui.metrics.metricLabel`).
Re-ran build → green. (During the fix I also had to recover from an accidental `git commit --amend`
that bundled the mobile fix into the frontend commit; split back into two clean per-site commits via
`git reset --soft HEAD~1` + re-amend of Site A + re-commit of Site B. Final history verified clean.)

## Site B — frontend offer/terms fully hardcoded Russian

Files:
- `frontend/messages/en.json`
- `frontend/messages/ru.json`
- `frontend/src/app/(landing)/offer/page.tsx`
- `frontend/src/app/(landing)/terms/page.tsx`

### Messages additions

`common` namespace — added `legalInfo` key (kept `home` reused, not duplicated):
- en: `"legalInfo": "Legal information"`
- ru: `"legalInfo": "Правовая информация"`

New `offer` namespace:
- en: `{ "title": "Offer", "comingSoon": "Document in preparation." }`
- ru: `{ "title": "Оферта", "comingSoon": "Документ готовится." }`

New `terms` namespace:
- en: `{ "title": "Terms of Service", "comingSoon": "Document in preparation." }`
- ru: `{ "title": "Пользовательское соглашение", "comingSoon": "Документ готовится." }`

`common.home` reused for breadcrumb "Главная" / "На главную" link. Kept separate `offer.comingSoon`
+ `terms.comingSoon` per brief (no new `legal` namespace).

### Page rewrites (offer + terms, identical structure)

Both converted to async server components using `getTranslations` from `next-intl/server`
(mirrors `legal-layout.tsx`):
- `const t = await getTranslations("offer")` / `"terms"`
- `const tCommon = await getTranslations("common")`
- breadcrumb: `tCommon("home")` > `tCommon("legalInfo")` > `t("title")`
- `<h1>`: `t("title")`
- `<p>` body: `t("comingSoon")`
- link: `{tCommon("home")} →` (arrow literal kept, locale-agnostic)

`metadata.title` left hardcoded Russian (out of scope per brief — static SEO meta, not visible body content).

Verify:
- `grep -c 'getTranslations' offer/page.tsx terms/page.tsx` → 3 each (1 import + 2 calls).
- `grep -nE 'Оферта|Пользовательское соглашение|Документ готовится|На главную|Правовая информация' offer/page.tsx terms/page.tsx`
  → only 2 matches, both `metadata.title` lines (`title: "Оферта — SkateLab"` / `title: "Пользовательское соглашение — SkateLab"`).
  Acceptable per brief.
- `cd frontend && bun install && bunx tsc --noEmit` → exit 0, clean.

Note: initial tsc run reported "Cannot find module 'next'" etc. because `node_modules` was not
installed in the fresh worktree. After `bun install`, tsc is fully clean. No type errors in any
file I touched (or anywhere else).

## Constraints honored
- Edited ONLY the 5 allowed files.
- Did NOT touch `privacy/page.tsx` or `metadata.title`.
- Matched existing patterns (`localizedMessage()` composable, `getTranslations` server pattern).
- Committed after each site with `fix(mobile):` / `fix(frontend):` convention.

## Concerns
None.