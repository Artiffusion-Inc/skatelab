# KMP Skill Improvements Design

> **Дата:** 2026-05-27  
> **Контекст:** Ревью skill `kmp-development` 5 специализированными агентами (Market Research, Architecture Review, Ban Enforcement, Compose Multiplatform, Skill Design Patterns)

---

## Executive Summary

5 агентов проанализировали skill с разных углов. Итог: skill сильнее рынка по глубине (BLE, CameraX, audit-команда, sealed AppError), но имеет 4 критических проблемы, ~15 важных улучшений и ~10 «nice to have». Приоритет — исправить критическое, добавить 4 новых reference-файла, расширить audit и исправить неточности в compose-multiplatform.md.

---

## 1. Критические проблемы (CRITICAL)

### C1. Закон #6 противоречит реальной архитектуре проекта

**Закон:** «Repository in shared, DB in platform. Room implementations in `androidMain`. iOS uses Keychain + UserDefaults via `multiplatform-settings`.»

**Реальность:** В проекте Room живёт в `androidApp/data/db/`, не в `shared/`. `libs.versions.toml` не содержит `room-runtime-multiplatform`. Закон описывает целевое состояние, которое ещё не реализовано.

**Решение:** Переписать закон #6 с разделением текущего и целевого состояния. Уточнить: «Room сейчас в androidApp. Миграция в shared/androidMain запланирована. iOS использует Keychain + UserDefaults через multiplatform-settings.»

### C2. Нет навигационной архитектуры

`android-ui.md` упоминает Navigation Compose (3 строки), `compose-multiplatform.md` упоминает Navigation 3. Но нет guidance по:
- Deep links и навигационным аргументам
- Восстановлению состояния навигации после смерти процесса
- Nested navigation graphs / multi-back-stack (bottom nav)
- Навигационному тестированию

**Решение:** Добавить раздел Navigation в `android-ui.md` (8-10 строк: типы маршрутов, deep links, process death restoration) + обновить `compose-multiplatform.md` с уточнением что Navigation 3 CMP — alpha, а не stable.

### C3. Нет CI/CD для KMP

Нет guidance по:
- GitHub Actions workflows для KMP (iOS simulator tests, Android instrumented tests, JVM tests)
- Gradle build caching в CI
- SKIE framework build requirements (Xcode version pinning)
- Test parallelism и sharding

**Решение:** Добавить секцию CI/CD в `gradle.md` (15-20 строк): GitHub Actions matrix, Gradle caching, SKIE build requirements, iOS simulator test command.

### C4. Устаревшие версии

Skill ссылается на: Kotlin 2.1.21, Ktor 3.1.3, Hilt 2.56.1. Актуальные стабильные: Kotlin 2.3.21, Ktor 3.5.0, Hilt 2.59.2. Skill отстаёт на 2+ минорные версии.

**Решение:** В `gradle.md` добавить примечание: «Версии ниже — project-pinned, не latest stable. Проверяй compatibility matrix перед обновлением.» Обновить конкретные версии в следующей итерации после тестирования.

---

## 2. Compose Multiplatform — неточности (из Агента 4)

### WRONG (обязательно исправить)

**Navigation 3 артефакт неверный.** Skill пишет `org.jetbrains.androidx.navigation:navigation-compose3` version `2.9.x`. Правильно: `org.jetbrains.androidx.navigation3:navigation3-ui` version `1.0.0-alpha05`. Navigation 3 для CMP — **alpha**, не production-ready.

### OUTDATED (обновить)

| Что | Проблема | Исправление |
|-----|----------|-------------|
| Kotlin для JS/Wasm | «2.3 for native/web» | Уточнить: 2.3.20 для JS/Wasm |
| CMP 1.11.0 breaking changes | Отсутствуют | Добавить: Shader wrapper, dropped x86_64, WebElementView → HtmlElementView, parallelRendering default |
| Navigation 3 зрелость | Не указана | Явно: «alpha для CMP, Navigation 2.9+ — stable» |
| adaptive-navigation3 | «available» | Уточнить версию: `1.3.0-alpha02` |
| Test v2 API | Неполный | Добавить `effectContext` параметр |

### MISSING (добавить)

| Что | Приоритет |
|-----|----------|
| **Hot Reload — desktop/JVM only** | Критический. Разработчики думают что работает на iOS |
| Hot Reload ограничения (ViewModel state, single IDE) | Высокий |
| Hot Reload runtime API (`AfterHotReloadEffect`) | Средний |
| **Wasm/web target секция** | Высокий (Beta статус, HtmlElementView) |
| `ComposeUIView` новый API (1.11.0) | Средний |
| Native iOS text input (experimental) | Средний |
| Polymorphic serialization для Nav 3 на iOS | Высокий |
| Dropped x86_64 support | Средний |

---

## 3. Архитектурные улучшения (из Агентов 2 + 5)

### I1. Расширить audit-команду

Добавить проверки:

| Новая проверка | Grep-паттерн | Причина |
|---------------|-------------|---------|
| `runBlocking` в commonMain | `commonMain` + `runBlocking` | Блокирует native thread |
| `java.util.UUID` в commonMain | `commonMain` + `import java.util.UUID` | JVM-only |
| `java.time` в commonMain | `commonMain` + `import java.time` | JVM-only |
| `Dispatchers.IO` в commonMain | `commonMain` + `Dispatchers.IO` | Android-only dispatcher |
| `StateFlow<UiEffect>` | `StateFlow<.*Effect` | Двойное потребление на config change |
| `@Entity` без `tableName` | `@Entity(` без `tableName` | Room KMP требует явное имя |
| `fallbackToDestructiveMigration` без DEBUG | `fallbackToDestructiveMigration` не в debug | Data loss в production |
| `@Parcelize` в commonMain | `commonMain` + `@Parcelize` | Android-only |
| `LocalContext.current` в shared Compose | `LocalContext.current` в shared/ | Android-only |
| hardcoded strings в UI composables | Строковые литералы в Compose | i18n violation |

### I2. Routing gap: нет команды `feature`

Самый частый KMP-задача — создание нового feature (DTO → Repository → ViewModel → UI → Navigation → Tests). Требует загрузку 3-4 reference-файлов. Нет единой точки входа.

**Решение:** Добавить команду `feature` в SKILL.md с маршрутизацией: load `shared-code.md` → `data-layer.md` → `android-ui.md` → `testing.md` последовательно.

### I3. Cross-reference: compose-multiplatform.md under-linked

compose-multiplatform.md имеет только 1 inbound-ссылку. Должна быть связана с:
- `shared-code.md` (ViewModels → Compose UI)
- `android-ui.md` (shared Compose vs Android-specific)
- `ios-ui.md` (Compose inside SwiftUI)

### I4. ios-ui.md формат ссылок

ios-ui.md использует backtick-формат (`android-ui.md`) вместо markdown-ссылок (`[text](file.md)`). Несогласованно с остальными reference-файлами.

### I5. `shared-code.md` — слишком широкий, слишком мелкий

Покрывает Ktor, auth, serialization, ViewModels, coroutines, Flow, error propagation — 7+ тем в одном файле. Каждая получает 10-15 строк.

**Решение:** Разделить на `networking.md` (Ktor, auth, serialization) и `viewmodels.md` (ViewModels, coroutines, Flow, state management). Это улучшит глубину без увеличения общего размера.

### I6. `platform-apis.md` — проектно-специфичный контент

WT901 service UUIDs, frame types, scale factors — это детали проекта, не общий KMP guidance.

**Решение:** Вынести проектно-специфичные константы в комментарий: «Project-specific: replace with your BLE service UUIDs.» Оставить общий Kable pattern.

---

## 4. Новые reference-файлы (высокий приоритет)

### N1. `navigation.md` — Навигация

Deep links, type-safe routes, process death restoration, nested graphs, bottom nav, Navigation 3 (alpha status), cross-module contracts, predictive back.

### N2. `i18n.md` — Локализация

String resources (kotlinx-resources или multiplatform-settings), plurals, RTL, locale-aware formatting, динамическая смена языка.

### N3. `security.md` — Безопасность

Certificate pinning (Ktor), network security config, API key management, encrypted storage (уже частично в data-layer.md, но разрозненно), ProGuard/R8 rules.

### N4. `logging.md` — Логирование и наблюдаемость

Kermit/Napier для multiplatform логирования, CrashlyticsTree (Android), os_log (iOS), sensitive data redaction, analytics event tracking из commonMain.

---

## 5. Skill Design: заимствования из impeccable

| Из impeccable | Что взять | Приоритет |
|-------------|---------|----------|
| Audit-скрипт | `scripts/audit.sh` — автоматический grep-check вместо ручного | Высокий |
| Template variables | `{{project_root}}`, `{{command_prefix}}` для portability | Средний |
| Pre-flight gates | Проверка source set hierarchy, version catalog, SKIE plugin перед кодом | Высокий |
| `feature` command | Полный stack: DTO → Repo → VM → UI → Nav → Tests | Высокий |

---

## 6. Skill Design: что мы делаем ЛУЧШЕ рынка

1. **Hardware/device API coverage** — Kable BLE, CameraX, WorkManager, IMU. Никто другой не покрывает.
2. **Enforceable bans** — grep-based audit с конкретными паттернами.
3. **Error handling depth** — полная sealed AppError иерархия + mapping rules.
4. **Testing strategy decision table** — когда fakes, Mokkery, MockEngine.
5. **Cross-reference network** — каждый reference ссылается на 8-10 других.
6. **Routing overlap documentation** — явные правила для пересекающихся команд.
7. **INDEX.md** — быстрый discovery layer.
8. **«Common mistake» callouts** — конкретные антипаттерны с решениями.

---

## 7. Приоритеты реализации

### P0 — Немедленно (критические и WRONG)

1. Исправить Navigation 3 артефакт (WRONG)
2. Исправить закон #6 (противоречие с проектом)
3. Добавить «Hot Reload — desktop/JVM only» в compose-multiplatform.md
4. Добавить Navigation 3 alpha status

### P1 — Следующая итерация

5. Расширить audit-команду (6-10 новых проверок)
6. Добавить `feature` команду в SKILL.md
7. Разделить `shared-code.md` на `networking.md` + `viewmodels.md`
8. Добавить cross-ссылки на compose-multiplatform.md
9. Исправить формат ссылок в ios-ui.md
10. Добавить CI/CD секцию в `gradle.md`
11. Добавить CMP 1.11.0 breaking changes в compose-multiplatform.md

### P2 — Будущие итерации

12. Новый `navigation.md` reference
13. Новый `i18n.md` reference
14. Новый `security.md` reference
15. Новый `logging.md` reference
16. Audit-скрипт `scripts/audit.sh`
17. Template variables в SKILL.md
18. Вынести WT901 константы из platform-apis.md
19. Добавить Wasm/web секцию в compose-multiplatform.md

---

## 5 агентов — сводка находок

| Агент | Ключевые находки |
|-------|-----------------|
| **Market Research** | 15 KMP skill источников. Наш сильнее по hardware, error handling, testing. Сильно не хватает: i18n, accessibility, security, navigation, logging, animations, performance, production/release |
| **Architecture Review** | 4 CRITICAL, 12 IMPORTANT, 7 NICE. Закон #6 противоречит проекту. Нет CI/CD, навигации, логирования. Версии устарели. shared-code.md слишком широкий |
| **Ban Enforcement** | 6 bans нуждаются в подкреплении с rationale. 4 закона неоднозначны. 6 новых бан-проверок (runBlocking, java.util.UUID, Dispatchers.IO, @Parcelize, LocalContext, hardcoded strings) |
| **Compose Multiplatform** | 1 WRONG (Navigation 3 артефакт). 5 OUTDATED. 9 MISSING (Hot Reload JVM-only, Wasm, ComposeUIView, native text input, Nav 3 alpha status). Актуально: CMP 1.11.0, iOS stable, @Preview |
| **Skill Design** | Token efficiency OK (~20K). Routing gap: нет `feature` команды. compose-multiplatform.md under-linked (1 ref). ios-ui.md backtick-формат. Audit grep-паттерны medium FP risk. Заимствовать из impeccable: audit-скрипт, template variables, pre-flight gates |